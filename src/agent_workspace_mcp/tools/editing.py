"""Editing tools for the Agent Workspace MCP."""

import re
import difflib
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
        security.validate_patch_security(patch_content)
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
            description='List of {"old": "search_text", "new": "replacement"} objects.'
        ),
    ],
    dry_run: Annotated[
        bool, Field(description="Preview changes as a diff without applying.")
    ] = False,
    ctx: Context = None,
) -> str:
    """Replace substrings in a file. Fallback to fuzzy whitespace matching if exact fails. Use this as primary tool to edit files.

    Returns unified diff. Validates .py, .json, .toml, .yaml syntax after edits.
    """
    try:
        path = security.safe_path(filepath)
        if ctx:
            await ctx.info(f"Search and replace in: {filepath} ({len(edits)} edits)")

        if not path.exists():
            return f"ERROR: File '{filepath}' not found."

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
                return f"ERROR: Edit {i} must contain 'old' and 'new' keys."
            
            if not old:
                return f"ERROR: Edit {i} has empty 'old' text. Insertion not supported via search_and_replace."

            old_norm = _normalize_line_endings(old)
            new_norm = _normalize_line_endings(new)

            # Try exact match first
            count = current_content.count(old_norm)
            if count == 1:
                current_content = current_content.replace(old_norm, new_norm, 1)
                exact_count += 1
            elif count > 1:
                return f"ERROR: Edit {i} ('{old[:20]}...') found {count} times (exact match). Make it unique."
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
                        return f"ERROR: Edit {i} ('{old[:20]}...') not found in '{filepath}' (tried exact and fuzzy matching)."
                except ValueError as e:
                    return f"ERROR: Edit {i}: {str(e)}"

        # Restore final newline if it existed in original content
        if original_content.endswith("\n") and not current_content.endswith("\n"):
            current_content += "\n"

        # 3. Validate syntax (only if content changed)
        if current_content != content:
            ext = path.suffix.lower()
            if ext == ".py":
                try:
                    ast.parse(current_content)
                except SyntaxError as e:
                    return f"ERROR: Python syntax error at line {e.lineno}: {e.msg}."
            elif ext == ".json":
                try:
                    json.loads(current_content)
                except json.JSONDecodeError as e:
                    return f"ERROR: JSON parse error at line {e.lineno}: {e.msg}."
            elif ext == ".toml":
                try:
                    tomllib.loads(current_content)
                except Exception as e:
                    return f"ERROR: TOML parse error: {str(e)}."
            elif ext in (".yaml", ".yml"):
                try:
                    import yaml
                    yaml.safe_load(current_content)
                except Exception as e:
                    return f"ERROR: YAML parse error: {str(e)}."

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
            return "No changes made (content matched existing)."

        # 5. Write if not dry_run
        match_stats = f"{len(edits)} edits ({exact_count} exact, {fuzzy_count} fuzzy-matched)"
        if not dry_run:
            temp_path = path.with_suffix(f"{path.suffix}.tmp")
            temp_path.write_text(current_content, encoding="utf-8")
            os.replace(temp_path, path)
            return f"Successfully applied {match_stats} to '{filepath}':\n\n{diff}"
        else:
            return f"DRY RUN - proposed changes for '{filepath}' ({match_stats}):\n\n{diff}"

    except Exception as e:
        if ctx:
            await ctx.error(f"Search and replace failed: {str(e)}")
        return f"ERROR: {str(e)}"
