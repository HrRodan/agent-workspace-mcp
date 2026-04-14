"""Filesystem tools for the Agent Workspace MCP."""

import os
import datetime
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
    """Read the contents of a file from the workspace.

    Args:
        filepath: Path to the file, relative to /workspace.
        ctx: Auto-injected FastMCP context.

    Returns:
        The content of the file as a string.
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
    content: Annotated[str, Field(description="String content to write to the file.")],
    ctx: Context,
) -> str:
    """Write content to a file in the workspace.

    Args:
        filepath: Path to the file, relative to /workspace.
        content: String content to write.
        ctx: Auto-injected FastMCP context.

    Returns:
        A success message with the number of bytes written.
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


async def list_directory(
    directory_path: Annotated[
        str, Field(description="Path to the directory, relative to /workspace.")
    ] = ".",
    ctx: Context = None,
) -> str:
    """List the contents of a directory in the workspace.

    Args:
        directory_path: Path to the directory, relative to /workspace.
        ctx: Auto-injected FastMCP context.

    Returns:
        A formatted listing of files and directories.
    """
    try:
        path = security.safe_path(directory_path)
        if ctx:
            await ctx.info(f"Listing directory: {directory_path}")

        if not path.exists():
            return f"ERROR: Directory '{directory_path}' not found."

        if not path.is_dir():
            return f"ERROR: '{directory_path}' is not a directory."

        entries = []
        for item in sorted(
            path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
        ):
            rel_path = item.relative_to(security.WORKSPACE_ROOT)
            if item.is_dir():
                entries.append(f"[DIR]  {rel_path}/")
            else:
                size = item.stat().st_size
                entries.append(f"[FILE] {rel_path} ({size} bytes)")

        if not entries:
            return f"Directory '{directory_path}' is empty."

        return "\n".join(entries)

    except Exception as e:
        if ctx:
            await ctx.error(f"Failed to list {directory_path}: {str(e)}")
        return f"ERROR: {str(e)}"


async def get_file_info(
    filepath: Annotated[
        str, Field(description="Path to the item, relative to /workspace.")
    ],
    ctx: Context,
) -> str:
    """Get metadata for a specific file or directory.

    Args:
        filepath: Path to the item, relative to /workspace.
        ctx: Auto-injected FastMCP context.

    Returns:
        Formatted info including size, modification time, and permissions.
    """
    try:
        path = security.safe_path(filepath)
        await ctx.info(f"Getting info for: {filepath}")

        if not path.exists():
            return f"ERROR: '{filepath}' not found."

        stats = path.stat()
        mod_time = datetime.datetime.fromtimestamp(
            stats.st_mtime, tz=datetime.timezone.utc
        ).isoformat()
        perms = oct(stats.st_mode & 0o777)
        item_type = "directory" if path.is_dir() else "file"

        info = [
            f"Path: {path.relative_to(security.WORKSPACE_ROOT)}",
            f"Size: {stats.st_size} bytes",
            f"Modified: {mod_time}",
            f"Permissions: {perms}",
            f"Type: {item_type}",
        ]
        return "\n".join(info)

    except Exception as e:
        await ctx.error(f"Failed to get info for {filepath}: {str(e)}")
        return f"ERROR: {str(e)}"


async def search_workspace(
    pattern: Annotated[str, Field(description="Glob pattern (e.g., '**/*.py').")],
    ctx: Context,
) -> str:
    """Search for files in the workspace using a glob pattern.

    Args:
        pattern: Glob pattern (e.g., '**/*.py').
        ctx: Auto-injected FastMCP context.

    Returns:
        A list of matching files, relative to /workspace.
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
