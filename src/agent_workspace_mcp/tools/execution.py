import asyncio
from typing import Annotated
from pydantic import Field
from fastmcp import Context
from agent_workspace_mcp.utils import security


async def run_bash(
    command: Annotated[str, Field(description="The bash command to execute.")],
    timeout: Annotated[
        int,
        Field(
            description="Seconds before the command is killed (defaults to COMMAND_TIMEOUT)."
        ),
    ] = None,
    ctx: Context = None,
) -> str:
    """Execute a shell command in the /workspace directory.

    Args:
        command: The bash command to execute.
        timeout: Seconds before the command is killed (defaults to COMMAND_TIMEOUT).
        ctx: Auto-injected FastMCP context.

    Returns:
        Combined stdout and stderr of the command.
    """
    if timeout is None:
        timeout = security.COMMAND_TIMEOUT

    if ctx:
        await ctx.info(f"Running command: {command}")

    try:
        # Use /bin/sh -c to execute the command string
        process = await asyncio.create_subprocess_exec(
            "/bin/sh",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
            cwd=str(security.WORKSPACE_ROOT),
        )

        try:
            # Wait for completion with timeout
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

            return output

        except asyncio.TimeoutError:
            # Kill the process if it timed out
            try:
                process.kill()
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
        str, Field(description="Path to lint, relative to /workspace.")
    ] = ".",
    ctx: Context = None,
) -> str:
    """Proactively execute ruff check and ruff format --check on the workspace.

    Args:
        path: Path to lint, relative to /workspace.
        ctx: Auto-injected FastMCP context.

    Returns:
        Lint and formatting diagnostics.
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
        if "All checks passed" not in check_output and check_output.strip():
            results.append("### Ruff Check:\n" + check_output)

        if "would reformat" in format_output or "error" in format_output.lower():
            results.append("### Ruff Format Check:\n" + format_output)

        if not results:
            return "✓ No lint or formatting issues found."

        return "\n\n".join(results)

    except Exception as e:
        error_msg = f"ERROR: Linting failed: {str(e)}"
        if ctx:
            await ctx.error(error_msg)
        return error_msg
