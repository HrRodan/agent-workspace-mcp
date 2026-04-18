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
    offset: Annotated[
        int, Field(description="Line offset to start reading from (0-based).")
    ] = 0,
    limit: Annotated[
        int, Field(description="Max lines to return. Default: 100.")
    ] = 100,
    ctx: Context = None,
) -> str:
    """Read a text file.

    Text only, max 1MB. Returns first 100 lines by default.
    For larger files or specific segments, use offset/limit or bash (grep/head/tail).
    """
    try:
        path = security.safe_path(filepath)
        if ctx:
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

        lines = content.splitlines()
        if limit > 0 or offset > 0:
            total_lines = len(lines)
            end = offset + limit if limit > 0 else total_lines
            lines = lines[offset:end]
            if ctx:
                await ctx.info(f"Read {len(lines)} lines (offset {offset}, total {total_lines})")

        return "\n".join(lines)

    except Exception as e:
        if ctx:
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
    ctx: Context = None,
) -> str:
    """Create or overwrite a file.

    Creates parent directories if needed. For partial edits, prefer search_and_replace.
    """
    try:
        path = security.safe_path(filepath)
        if ctx:
            await ctx.info(f"Writing to file: {filepath}")

        # Ensure parent directories exist
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, path)

        return f"Successfully wrote {len(content.encode('utf-8'))} bytes to {filepath}"

    except Exception as e:
        if ctx:
            await ctx.error(f"Failed to write to {filepath}: {str(e)}")
        return f"ERROR: {str(e)}"


async def list_directory(
    path: Annotated[
        str,
        Field(description="Directory path, relative to /workspace. Default: '.'"),
    ] = ".",
    ctx: Context = None,
) -> str:
    """List files and directories. Returns [F] or [D] prefix.

    Excludes .git, .venv, etc. by default.
    """
    try:
        abs_path = security.safe_path(path)
        if ctx:
            await ctx.info(f"Listing directory: {path}")

        if not abs_path.exists():
            return f"ERROR: Path '{path}' not found."
        if not abs_path.is_dir():
            return f"ERROR: '{path}' is not a directory."

        entries = []
        for item in abs_path.iterdir():
            if item.name in security.SEARCH_EXCLUDE_DIRS:
                continue
            prefix = "[D]" if item.is_dir() else "[F]"
            entries.append(f"{prefix} {item.name}")

        if not entries:
            return "Directory is empty."

        return "\n".join(sorted(entries))

    except Exception as e:
        if ctx:
            await ctx.error(f"List directory failed: {str(e)}")
        return f"ERROR: {str(e)}"






async def search_workspace(
    pattern: Annotated[
        str,
        Field(description="Glob pattern for paths (e.g. 'src/**/*.py')."),
    ],
    exclude_patterns: Annotated[
        list[str],
        Field(description="Additional glob patterns to exclude."),
    ] = [],
    ctx: Context = None,
) -> str:
    """Find files by glob pattern (name/path only).

    Returns up to 50 paths. For content search use `run_bash('grep -rn ...')`.
    """
    try:
        security.validate_glob_pattern(pattern)
        
        root_dir = os.path.realpath(str(security.WORKSPACE_ROOT))
        if ctx:
            await ctx.info(f"Searching for pattern: {pattern}")

        matches = []
        truncated = False
        count = 0
        from pathlib import PurePath
        from fnmatch import fnmatch

        # We discovery files using os.walk (controlled navigation)
        # and then filter in-memory using PurePath.match (safe string matching)
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Prune excluded directories in-place to avoid walking into them
            dirnames[:] = [d for d in dirnames if d not in security.SEARCH_EXCLUDE_DIRS]
            
            # Calculate relative path of the current directory
            rel_dir = os.path.relpath(dirpath, root_dir)
            if rel_dir == ".":
                rel_dir = ""

            for filename in filenames:
                rel_path = os.path.join(rel_dir, filename) if rel_dir else filename
                
                # Check user exclusions first
                if exclude_patterns and any(fnmatch(rel_path, p) for p in exclude_patterns):
                    continue

                # Use PurePath.match for secure glob pattern matching (string only)
                # We also check the pattern with '**/ ' removed to match zero directories for '**'
                if PurePath(rel_path).match(pattern) or (
                    "**" in pattern and PurePath(rel_path).match(pattern.replace("**/", ""))
                ):
                    if count >= security.MAX_SEARCH_RESULTS:
                        truncated = True
                        break
                    matches.append(rel_path)
                    count += 1
            
            if truncated:
                break

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
        if ctx:
            await ctx.error(f"Search failed: {str(e)}")
        return f"ERROR: {str(e)}"
