"""Execution tools for the Agent Workspace MCP."""

import os
import signal
import asyncio
import logging
from typing import Annotated
from pydantic import Field
from fastmcp import Context
from agent_workspace_mcp.utils import security
from agent_workspace_mcp.tools import _logging

logger = logging.getLogger(__name__)


async def run_bash(
    command: Annotated[
        str,
        Field(
            description=(
                "The shell command to execute. "
                "All Python operations MUST use `uv` (see tool description for details)."
            )
        ),
    ],
    timeout: Annotated[
        int,
        Field(
            description=(
                "Max seconds before the command is killed. "
                "Default: 60s. Increase for long builds or large downloads."
            )
        ),
    ] = None,
    ctx: Context = None,
) -> str:
    """Execute a shell command in the sandboxed /workspace directory.

    Environment:
    - Working directory: /workspace (all relative paths resolve here).
    - Shell: /bin/sh. Supports pipes, redirects, &&, ||, etc.
    - Available commands: standard bash e.g. curl, git, jq, patch, tree, fd-find (fd), ripgrep (rg), procps (ps, kill, pkill), zip, unzip, tar, ...
    - Output: Returns "[Exit code: N]" followed by merged stdout+stderr.
      Output is truncated at 50 KB — use `head`, `tail`, or `grep` for large outputs.
    - Timeout: The process is killed after `timeout` seconds (default 60s).

    Python & Dependency Management (CRITICAL — uv only):
    - Run a script:        `uv run script.py`       (NOT `python script.py`)
    - Add a dependency:    `uv add <pkg>`            (NOT `pip install`)
    - Remove a dependency: `uv remove <pkg>`
    - Install a CLI tool:  `uv tool install <pkg>`   (NOT `pipx`)
    - Run a one-off tool:  `uvx <tool>`              (e.g., `uvx ruff check .`)
    - Init a new project:  `uv init`
    - Sync environment:    `uv sync`
    `python` and `pip` are NOT available. Always use `uv`.
    """
    if timeout is None:
        timeout = security.COMMAND_TIMEOUT

    start_time = _logging.log_tool_entry(logger, "run_bash", command=command, timeout=timeout)
    if ctx:
        await ctx.info(f"Running command: {command}")

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

            error_msg = f"ERROR: Command timed out after {timeout}s. The process was killed. Simplify the command or increase timeout."
            _logging.log_tool_exit(logger, "run_bash", start_time, success=False, summary="Timeout", output=error_msg)
            if ctx:
                await ctx.error(error_msg)
            return error_msg

    except Exception as e:
        error_msg = f"ERROR: Failed to execute command: {str(e)}"
        if "start_time" in locals():
            _logging.log_tool_exit(logger, "run_bash", start_time, success=False, summary=str(e), output=error_msg)
        if ctx:
            await ctx.error(error_msg)
        return error_msg



