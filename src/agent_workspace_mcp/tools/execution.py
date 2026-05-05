"""Execution tools for the Agent Workspace MCP."""

import os
import signal
import asyncio
import logging
from typing import Annotated
from pydantic import Field
from fastmcp import Context
from fastmcp.exceptions import ToolError
from agent_workspace_mcp.utils import security
from agent_workspace_mcp.tools import _logging

logger = logging.getLogger(__name__)


async def run_bash(
    command: Annotated[
        str,
        Field(
            description="Shell command to execute."
        ),
    ],
    timeout: Annotated[
        int,
        Field(
            description="Max seconds before kill. Increase for long builds."
        ),
    ] = None,
    ctx: Context = None,
) -> str:
    """Run a shell command in /workspace. Returns [Exit code: N] + merged stdout/stderr, truncated at 50KB.

    Tools: curl, git, jq, patch, tree, fd, rg, zip, tar and standard coreutils. Supports pipes, redirects, &&, ||.

    Python/packages (uv only — no python/pip):
      uv run script.py     Run scripts (auto-installs deps from imports)
      uv add/remove <pkg>  Manage project dependencies
      uv init              Scaffold new project with pyproject.toml
      uvx <tool>           Run CLI tools without install (e.g. uvx ruff check .)
    """
    if timeout is None:
        timeout = security.COMMAND_TIMEOUT

    start_time = _logging.log_tool_entry(logger, "run_bash", command=command, timeout=timeout)
    if ctx:
        await ctx.info(f"Running command: {command}")

    # Intercept command via RTK for token optimization
    try:
        import shutil
        rtk_path = shutil.which("rtk")
        if rtk_path:
            # Check if rtk can rewrite the command
            rtk_check = await asyncio.create_subprocess_exec(
                rtk_path, "rewrite", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_bytes, _ = await asyncio.wait_for(rtk_check.communicate(), timeout=2.0)
            
            # rtk rewrite exits 0 or 3 on success, and outputs the rewritten command
            if rtk_check.returncode in (0, 3) and stdout_bytes:
                optimized_cmd = stdout_bytes.decode("utf-8").strip()
                if optimized_cmd and optimized_cmd != command:
                    command = optimized_cmd
                    if ctx:
                        await ctx.info(f"RTK optimized command: {command}")
    except Exception as e:
        logger.debug(f"RTK rewrite check failed: {e}")

    try:
        # Use /bin/sh -c to execute the command string in a new process group
        # start_new_session=True creates a new process group, allowing us to kill children
        process = await asyncio.create_subprocess_exec(
            "/bin/sh",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
            cwd=str(security.WORKSPACE_ROOT),
            start_new_session=True,
        )

        try:
            # Wait for completion with timeout. communicate() reads until EOF.
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")

            return_code = process.returncode
            if ctx:
                await ctx.info(f"Command finished with exit code: {return_code}")

            # Truncate output if necessary (limit to 50KB as per requirements)
            max_size = 50 * 1024
            if len(output) > max_size:
                output = (
                    output[:max_size]
                    + "\n... output truncated at 50KB. Use 'head' or 'tail' to view specific portions."
                )

            # Return exit code and output
            result = f"[Exit code: {return_code}]"
            if output:
                result += f"\n{output}"
            
            _logging.log_tool_exit(
                logger, 
                "run_bash", 
                start_time, 
                success=True, 
                summary=f"exit_code={return_code}, output_len={len(output)}",
                output=result
            )
            return result

        except asyncio.TimeoutError:
            # Kill the entire process group if it timed out to reaps children (like uv workers)
            try:
                os.killpg(process.pid, signal.SIGKILL)
                # Still wait for the main process to be reaped
                await process.wait()
            except ProcessLookupError:
                pass

            error_msg = f"Command timed out after {timeout}s. The process was killed. Simplify the command or increase timeout."
            _logging.log_tool_exit(logger, "run_bash", start_time, success=False, summary="Timeout", output=error_msg)
            if ctx:
                await ctx.error(error_msg)
            raise ToolError(error_msg)

    except ToolError:
        raise
    except Exception as e:
        error_msg = f"Failed to execute command: {str(e)}"
        if "start_time" in locals():
            _logging.log_tool_exit(logger, "run_bash", start_time, success=False, summary=str(e), output=error_msg)
        if ctx:
            await ctx.error(error_msg)
        raise ToolError(error_msg)



