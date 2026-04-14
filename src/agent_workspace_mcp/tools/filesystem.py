"""Filesystem tools for the Agent Workspace MCP."""

import os
from typing import Annotated
from pydantic import Field
from fastmcp import Context
from agent_workspace_mcp.utils import security


async def read_file(
    filepath: Annotated[
        str, Field(description="Path to the file, relative to /workspace.")
    ],
    ctx: Context,
) -> str:
    """Read a text file and return its contents as a plain string.

    Returns the raw file content without line numbers. Text files only —
    binary files are rejected. Maximum file size: 1 MB. For larger files,
    use `run_bash` with `head`, `tail`, or `grep` to read specific portions.
    """
    try:
        path = security.safe_path(filepath)
        await ctx.info(f"Reading file: {filepath}")

        if not path.exists():
            return f"ERROR: File '{filepath}' not found. Use list_directory() to discover available files."

        if path.is_dir():
            return f"ERROR: '{filepath}' is a directory. Use list_directory() to see its contents."

        if security.is_binary(path):
            return f"ERROR: File '{filepath}' appears to be binary. read_file only supports text files."

        file_size = path.stat().st_size
        if file_size > security.MAX_READ_SIZE_BYTES:
            return (
                f"ERROR: File '{filepath}' ({file_size} bytes) exceeds MAX_READ_SIZE_BYTES "
                f"({security.MAX_READ_SIZE_BYTES}). Use shell commands like 'head' or 'grep' to process it."
            )

        # Use errors="replace" to avoid crashing on invalid UTF-8 sequences in text files
        content = path.read_text(encoding="utf-8", errors="replace")
        return content

    except Exception as e:
        await ctx.error(f"Failed to read {filepath}: {str(e)}")
        return f"ERROR: {str(e)}"


async def write_file(
    filepath: Annotated[
        str, Field(description="Path to the file, relative to /workspace.")
    ],
    content: Annotated[
        str,
        Field(description="The complete file content to write."),
    ],
    ctx: Context,
) -> str:
    """Create or overwrite a file with the given content.

    Creates the file and any missing parent directories if they don't exist.
    If the file already exists, it is fully replaced. The write is atomic
    (temp file + rename) so readers never see a partial write.

    For targeted edits to an existing file, prefer `search_and_replace`.
    """
    try:
        path = security.safe_path(filepath)
        await ctx.info(f"Writing to file: {filepath}")

        # Ensure parent directories exist
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file then rename
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, path)

        return f"Successfully wrote {len(content.encode('utf-8'))} bytes to {filepath}"

    except Exception as e:
        await ctx.error(f"Failed to write to {filepath}: {str(e)}")
        return f"ERROR: {str(e)}"






async def search_workspace(
    pattern: Annotated[
        str,
        Field(
            description=(
                "Glob pattern to match file paths. "
                "Examples: '**/*.py' (all Python files), 'src/**/*.json', '*.md'."
            )
        ),
    ],
    ctx: Context,
) -> str:
    """Find files by name/path pattern (glob). Does NOT search file contents.

    Returns up to 50 matching file paths relative to /workspace.
    Common directories (.git, __pycache__, .venv) are excluded automatically.

    To search inside files by content, use `run_bash` with `grep -r "pattern" .`.
    """
    try:
        await ctx.info(f"Searching for pattern: {pattern}")

        matches = []
        truncated = False

        # We search relative to security.WORKSPACE_ROOT
        # We need to manually count to handle truncation correctly
        count = 0
        for path in security.WORKSPACE_ROOT.glob(pattern):
            # Check if any parent directory is in security.SEARCH_EXCLUDE_DIRS
            if any(
                part in security.SEARCH_EXCLUDE_DIRS
                for part in path.relative_to(security.WORKSPACE_ROOT).parts
            ):
                continue

            if path.is_file():
                if count >= security.MAX_SEARCH_RESULTS:
                    truncated = True
                    break
                matches.append(str(path.relative_to(security.WORKSPACE_ROOT)))
                count += 1

        if not matches:
            return f"No files found matching pattern '{pattern}'."

        result = [f"Found {len(matches)} matches:"]
        result.extend(matches)

        if truncated:
            result.append(
                f"... truncated at {security.MAX_SEARCH_RESULTS} results. Narrow your pattern."
            )

        return "\n".join(result)

    except Exception as e:
        await ctx.error(f"Search failed: {str(e)}")
        return f"ERROR: {str(e)}"
