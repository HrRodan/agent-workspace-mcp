"""Editing tools for the Agent Workspace MCP."""

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
        str,
        Field(description="Unified diff in standard patch format. Paths relative to /workspace."),
    ],
    ctx: Context = None,
) -> str:
    """Apply a unified diff (`patch -p1`) to workspace files.

    For single edits, prefer search_and_replace (includes syntax validation).
    """
    temp_patch = None
    try:
        if ctx:
            await ctx.info("Applying patch...")

        # Create a temporary patch file in the system temp directory
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            tmp.write(patch_content)
            temp_patch = tmp.name

        # Execute patch -p1 < temp_patch
        # We use run_bash to leverage its execution logic and timeout
        command = f"patch -p1 < {temp_patch}"
        result = await run_bash(command, timeout=security.COMMAND_TIMEOUT, ctx=ctx)

        return result

    except Exception as e:
        if ctx:
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
    edits: Annotated[
        list[dict[str, str]],
        Field(
            description='List of {"old": "exact_text", "new": "replacement"} objects.'
        ),
    ],
    dry_run: Annotated[
        bool, Field(description="Preview changes as a diff without applying.")
    ] = False,
    ctx: Context = None,
) -> str:
    """Replace exact substrings in a file. Matches must be unique.

    Returns unified diff. Validates .py, .json, .toml, .yaml syntax after edits.
    """
    try:
        path = security.safe_path(filepath)
        if ctx:
            await ctx.info(f"Search and replace in: {filepath} ({len(edits)} edits)")

        if not path.exists():
            return f"ERROR: File '{filepath}' not found."

        # 1. Read content
        content = path.read_text(encoding="utf-8", errors="replace")
        new_content = content

        # 2. Apply edits sequentially
        for i, edit in enumerate(edits):
            old = edit.get("old")
            new = edit.get("new")
            if old is None or new is None:
                return f"ERROR: Edit {i} must contain 'old' and 'new' keys."

            count = new_content.count(old)
            if count == 0:
                return f"ERROR: Edit {i} ('{old[:20]}...') not found in '{filepath}'."
            if count > 1:
                return f"ERROR: Edit {i} ('{old[:20]}...') found {count} times. Make it unique."

            new_content = new_content.replace(old, new, 1)

        # 3. Validate syntax (only if content changed)
        if new_content != content:
            ext = path.suffix.lower()
            if ext == ".py":
                try:
                    ast.parse(new_content)
                except SyntaxError as e:
                    return f"ERROR: Python syntax error at line {e.lineno}: {e.msg}."
            elif ext == ".json":
                try:
                    json.loads(new_content)
                except json.JSONDecodeError as e:
                    return f"ERROR: JSON parse error at line {e.lineno}: {e.msg}."
            elif ext == ".toml":
                try:
                    tomllib.loads(new_content)
                except Exception as e:
                    return f"ERROR: TOML parse error: {str(e)}."
            elif ext in (".yaml", ".yml"):
                try:
                    import yaml
                    yaml.safe_load(new_content)
                except Exception as e:
                    return f"ERROR: YAML parse error: {str(e)}."

        # 4. Generate diff
        import difflib
        diff = "".join(
            difflib.unified_diff(
                content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{filepath}",
                tofile=f"b/{filepath}",
            )
        )

        if not diff:
            return "No changes made (content matched existing)."

        # 5. Write if not dry_run
        if not dry_run:
            temp_path = path.with_suffix(f"{path.suffix}.tmp")
            temp_path.write_text(new_content, encoding="utf-8")
            os.replace(temp_path, path)
            return f"Successfully applied {len(edits)} edits to '{filepath}':\n\n{diff}"
        else:
            return f"DRY RUN - proposed changes for '{filepath}':\n\n{diff}"

    except Exception as e:
        if ctx:
            await ctx.error(f"Search and replace failed: {str(e)}")
        return f"ERROR: {str(e)}"
