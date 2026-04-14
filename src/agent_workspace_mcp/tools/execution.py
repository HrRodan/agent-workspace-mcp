"""Execution tools for the Agent Workspace MCP."""

import os
import signal
import asyncio
from typing import Annotated
from pydantic import Field
from fastmcp import Context
from agent_workspace_mcp.utils import security


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
            if ctx:
                await ctx.error(error_msg)
            return error_msg

    except Exception as e:
        error_msg = f"ERROR: Failed to execute command: {str(e)}"
        if ctx:
            await ctx.error(error_msg)
        return error_msg


async def lint_workspace(
    path: Annotated[
        str,
        Field(
            description=(
                "File or directory to lint, relative to /workspace. "
                "Defaults to '.' (entire workspace)."
            )
        ),
    ] = ".",
    ctx: Context = None,
) -> str:
    """Run Python linting and format-checking on workspace files.

    Call this after creating or modifying Python files to catch errors early.
    Runs two passes:
    1. `ruff check` — lint rules (unused imports, type errors, style violations).
    2. `ruff format --check` — formatting compliance (does NOT auto-fix).

    Returns "No lint or formatting issues found" when clean, or the full
    diagnostics with file paths and line numbers when issues are detected.
    """
    try:
        resolved_path = security.safe_path(path)
        rel_path = str(resolved_path.relative_to(security.WORKSPACE_ROOT))

        if ctx:
            await ctx.info(f"Linting path: {rel_path}")

        # Run ruff check
        check_cmd = f"uvx ruff check {rel_path}"
        check_output = await run_bash(
            check_cmd, timeout=security.COMMAND_TIMEOUT, ctx=ctx
        )

        # Run ruff format --check
        format_cmd = f"uvx ruff format --check {rel_path}"
        format_output = await run_bash(
            format_cmd, timeout=security.COMMAND_TIMEOUT, ctx=ctx
        )

        results = []
        # Check for non-zero exit code in run_bash output
        if "[Exit code: 0]" not in check_output:
            results.append("### Ruff Check:\n" + check_output)

        if "[Exit code: 0]" not in format_output:
            results.append("### Ruff Format Check:\n" + format_output)

        if not results:
            return "✓ No lint or formatting issues found."

        return "\n\n".join(results)

    except Exception as e:
        error_msg = f"ERROR: Linting failed: {str(e)}"
        if ctx:
            await ctx.error(error_msg)
        return error_msg
