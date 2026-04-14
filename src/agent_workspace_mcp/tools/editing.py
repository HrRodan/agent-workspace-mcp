import os
import ast
import json
import tomllib
import tempfile
from typing import Annotated
from pydantic import Field
from fastmcp import Context
from agent_workspace_mcp.utils import security
from agent_workspace_mcp.tools.execution import run_bash


async def apply_patch(
    patch_content: Annotated[
        str, Field(description="The content of the unified diff.")
    ],
    ctx: Context,
) -> str:
    """Apply a Unified Diff (.patch format) to the workspace using the native 'patch' utility.

    Args:
        patch_content: The content of the unified diff.
        ctx: Auto-injected FastMCP context.

    Returns:
        The output of the patch command or an error message.
    """
    temp_patch = None
    try:
        await ctx.info("Applying patch...")

        # Create a temporary patch file in /tmp (which should be tmpfs in container)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, dir="/tmp"
        ) as tmp:
            tmp.write(patch_content)
            temp_patch = tmp.name

        # Execute patch -p1 < temp_patch
        # We use run_bash to leverage its execution logic and timeout
        command = f"patch -p1 < {temp_patch}"
        result = await run_bash(command, timeout=security.COMMAND_TIMEOUT, ctx=ctx)

        return result

    except Exception as e:
        await ctx.error(f"Failed to apply patch: {str(e)}")
        return f"ERROR: {str(e)}"
    finally:
        if temp_patch and os.path.exists(temp_patch):
            try:
                os.remove(temp_patch)
            except Exception:
                pass


async def search_and_replace(
    filepath: Annotated[
        str, Field(description="Path to the file, relative to /workspace.")
    ],
    exact_search_block: Annotated[
        str, Field(description="The exact string to search for (must be unique).")
    ],
    replace_block: Annotated[str, Field(description="The string to replace it with.")],
    ctx: Context,
) -> str:
    """Swap a specific string block in a file with a replacement block.

    Args:
        filepath: Path to the file, relative to /workspace.
        exact_search_block: The exact string to search for (must be unique).
        replace_block: The string to replace it with.
        ctx: Auto-injected FastMCP context.

    Returns:
        A success message or an actionable error message.
    """
    try:
        path = security.safe_path(filepath)
        await ctx.info(f"Search and replace in: {filepath}")

        if not path.exists():
            return f"ERROR: File '{filepath}' not found."

        if path.is_dir():
            return f"ERROR: '{filepath}' is a directory."

        # 1. Read content
        content = path.read_text(encoding="utf-8", errors="replace")

        # 2. Count occurrences
        count = content.count(exact_search_block)
        if count == 0:
            return (
                f"ERROR: Search block not found in '{filepath}'. "
                f"Use read_file to verify exact content including whitespace."
            )
        if count > 1:
            return (
                f"ERROR: Search block found {count} times in '{filepath}'. "
                f"Provide more context in your search block to make it unique."
            )

        # 3. Replace in-memory
        new_content = content.replace(exact_search_block, replace_block, 1)

        # 4. Validate syntax
        ext = path.suffix.lower()
        if ext == ".py":
            try:
                ast.parse(new_content)
            except SyntaxError as e:
                return f"ERROR: Python syntax error at line {e.lineno}: {e.msg}. Fix and retry."
        elif ext == ".json":
            try:
                json.loads(new_content)
            except json.JSONDecodeError as e:
                return f"ERROR: JSON parse error at line {e.lineno}, col {e.colno}: {e.msg}. Fix and retry."
        elif ext == ".toml":
            try:
                tomllib.loads(new_content)
            except tomllib.TOMLDecodeError as e:
                return f"ERROR: TOML parse error: {str(e)}. Fix and retry."

        # 5. Write atomically
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(new_content, encoding="utf-8")
        os.replace(temp_path, path)

        return f"Successfully replaced content in '{filepath}'. {len(replace_block)} chars written."

    except Exception as e:
        await ctx.error(f"Search and replace failed: {str(e)}")
        return f"ERROR: {str(e)}"
