"""Editing tools for the Agent Workspace MCP."""

import re
import difflib
import os
import logging
from typing import Annotated
from pydantic import Field
from fastmcp import Context
from fastmcp.exceptions import ToolError
from agent_workspace_mcp.utils import security
from agent_workspace_mcp.tools import _logging, validation

logger = logging.getLogger(__name__)


def _normalize_line_endings(text: str) -> str:
    """Normalize \r\n to \n for consistent matching."""
    return text.replace("\r\n", "\n")


def _find_fuzzy_match(
    content_lines: list[str],
    old_lines: list[str],
) -> int | None:
    """Find the starting index where old_lines matches content_lines with whitespace-normalized comparison.

    Returns the 0-based line index of the first match, or None if no match is found.
    Raises ValueError if multiple matches are found (ambiguity).
    """
    if not old_lines:
        return None

    matches = []
    n = len(content_lines)
    m = len(old_lines)

    for i in range(n - m + 1):
        potential_match = content_lines[i : i + m]
        is_match = True
        for j in range(m):
            # Compare lines ignoring leading/trailing whitespace
            if old_lines[j].strip() != potential_match[j].strip():
                is_match = False
                break

        if is_match:
            matches.append(i)

    if len(matches) > 1:
        raise ValueError(f"Found {len(matches)} fuzzy matches. Make search text more unique.")

    return matches[0] if matches else None


def _apply_with_indent_preservation(
    content_lines: list[str],
    match_start: int,
    old_lines: list[str],
    new_lines: list[str],
) -> list[str]:
    """Replace matched lines while preserving detected indentation style.
    
    Rebases the replacement text so that its first line matches the indentation 
    of the first matched line in the file, and subsequent lines maintain their 
    relative indentation to that first line.
    """
    if not new_lines or match_start >= len(content_lines):
        return content_lines

    # Original indentation of the first matched line in the file
    first_content_line = content_lines[match_start]
    c_match = re.match(r"^(\s*)", first_content_line)
    original_indent = c_match.group(1) if c_match else ""

    # Indentation of the first line in the REPLACEMENT text (to use as base)
    first_new_line = new_lines[0]
    n_match = re.match(r"^(\s*)", first_new_line)
    new_base_indent = n_match.group(1) if n_match else ""

    processed_new_lines = []
    for line in new_lines:
        curr_match = re.match(r"^(\s*)", line)
        curr_indent = curr_match.group(1) if curr_match else ""
        
        # Calculate relative depth to the replacement's own base
        relative_delta = len(curr_indent) - len(new_base_indent)
        
        if relative_delta > 0:
            target_indent = original_indent + (" " * relative_delta)
        elif relative_delta < 0:
            trim_len = abs(relative_delta)
            target_indent = original_indent[:-trim_len] if len(original_indent) >= trim_len else ""
        else:
            target_indent = original_indent
            
        processed_new_lines.append(target_indent + line.lstrip())

    result = list(content_lines)
    result[match_start : match_start + len(old_lines)] = processed_new_lines
    return result


async def search_and_replace(
    filepath: Annotated[
        str, Field(description="File path relative to /workspace.")
    ],
    edits: Annotated[
        list[dict[str, str]],
        Field(
            description='[{"old": "exact_text", "new": "replacement"}]'
        ),
    ],
    dry_run: Annotated[
        bool, Field(description="Preview diff without applying.")
    ] = False,
    ctx: Context = None,
) -> str:
    """Primary file editing tool — prefer over patch. Replaces substrings with fuzzy whitespace fallback. Returns unified diff. Validates .py/.json/.toml/.yaml syntax."""
    try:
        path = security.safe_path(filepath)
        start_time = _logging.log_tool_entry(logger, "search_and_replace", filepath=filepath, edit_count=len(edits), dry_run=dry_run)
        if ctx:
            await ctx.info(f"Search and replace in: {filepath} ({len(edits)} edits)")

        if not path.exists():
            res = f"File '{filepath}' not found."
            _logging.log_tool_exit(logger, "search_and_replace", start_time, success=False, summary=res, output=res)
            raise ToolError(res)

        # 1. Read content and normalize line endings for matching
        original_content = path.read_text(encoding="utf-8", errors="replace")
        content = _normalize_line_endings(original_content)
        current_content = content
        
        fuzzy_count = 0
        exact_count = 0

        # 2. Apply edits sequentially
        for i, edit in enumerate(edits):
            old = edit.get("old")
            new = edit.get("new")
            if old is None or new is None:
                res = f"Edit {i} must contain 'old' and 'new' keys."
                _logging.log_tool_exit(logger, "search_and_replace", start_time, success=False, summary=res, output=res)
                raise ToolError(res)
            
            if not old:
                res = f"Edit {i} has empty 'old' text. Insertion not supported via search_and_replace."
                _logging.log_tool_exit(logger, "search_and_replace", start_time, success=False, summary=res, output=res)
                raise ToolError(res)

            old_norm = _normalize_line_endings(old)
            new_norm = _normalize_line_endings(new)

            # Try exact match first
            count = current_content.count(old_norm)
            if count == 1:
                current_content = current_content.replace(old_norm, new_norm, 1)
                exact_count += 1
            elif count > 1:
                res = f"Edit {i} ('{old[:20]}...') found {count} times (exact match). Make it unique."
                _logging.log_tool_exit(logger, "search_and_replace", start_time, success=False, summary=res, output=res)
                raise ToolError(res)
            else:
                # Try fuzzy whitespace match fallback
                content_lines = current_content.splitlines()
                old_lines = old_norm.splitlines()
                new_lines = new_norm.splitlines()

                try:
                    match_start = _find_fuzzy_match(content_lines, old_lines)
                    if match_start is not None:
                        updated_lines = _apply_with_indent_preservation(
                            content_lines, match_start, old_lines, new_lines
                        )
                        current_content = "\n".join(updated_lines)
                        fuzzy_count += 1
                    else:
                        res = f"Edit {i} ('{old[:20]}...') not found in '{filepath}' (tried exact and fuzzy matching)."
                        _logging.log_tool_exit(logger, "search_and_replace", start_time, success=False, summary=res, output=res)
                        raise ToolError(res)
                except ValueError as e:
                    res = f"Edit {i}: {str(e)}"
                    _logging.log_tool_exit(logger, "search_and_replace", start_time, success=False, summary=res, output=res)
                    raise ToolError(res)

        # Restore final newline if it existed in original content
        if original_content.endswith("\n") and not current_content.endswith("\n"):
            current_content += "\n"

        # 3. Validate syntax (only if content changed)
        if current_content != content:
            syntax_error = validation.validate_syntax(current_content, filepath)
            if syntax_error:
                _logging.log_tool_exit(logger, "search_and_replace", start_time, success=False, summary=syntax_error, output=syntax_error)
                raise ToolError(syntax_error)

        # 4. Generate diff (using 3 lines of context)
        diff = "".join(
            difflib.unified_diff(
                content.splitlines(keepends=True),
                current_content.splitlines(keepends=True),
                fromfile=f"a/{filepath}",
                tofile=f"b/{filepath}",
                n=3,
            )
        )

        if not diff:
            res = "No changes made (content matched existing)."
            _logging.log_tool_exit(logger, "search_and_replace", start_time, success=True, summary=res, output=res)
            return res

        # 5. Write if not dry_run
        match_stats = f"{len(edits)} edits ({exact_count} exact, {fuzzy_count} fuzzy-matched)"
        if not dry_run:
            temp_path = path.with_suffix(f"{path.suffix}.tmp")
            temp_path.write_text(current_content, encoding="utf-8")
            os.replace(temp_path, path)
            res_msg = f"Successfully applied {match_stats} to '{filepath}':\n\n{diff}"
            _logging.log_tool_exit(logger, "search_and_replace", start_time, success=True, summary=match_stats, output=res_msg)
            return res_msg
        else:
            res_msg = f"DRY RUN - proposed changes for '{filepath}' ({match_stats}):\n\n{diff}"
            _logging.log_tool_exit(logger, "search_and_replace", start_time, success=True, summary=f"DRY RUN: {match_stats}", output=res_msg)
            return res_msg

    except ToolError:
        raise
    except Exception as e:
        if "start_time" in locals():
            _logging.log_tool_exit(logger, "search_and_replace", start_time, success=False, summary=str(e), output=str(e))
        if ctx:
            await ctx.error(f"Search and replace failed: {str(e)}")
        raise ToolError(f"Search and replace failed: {str(e)}")
