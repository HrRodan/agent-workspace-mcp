"""Security and path validation utilities for the Agent Workspace MCP."""

import os
import re
from pathlib import Path

# The workspace root is hardcoded to /workspace for the containerized environment.
# Tests can still dynamically override this variable using monkeypatch.
WORKSPACE_ROOT: Path = Path("/workspace")

COMMAND_TIMEOUT: int = int(os.environ.get("COMMAND_TIMEOUT", "60"))
MAX_SEARCH_RESULTS: int = int(os.environ.get("MAX_SEARCH_RESULTS", "50"))
MAX_READ_SIZE_BYTES: int = int(os.environ.get("MAX_READ_SIZE_BYTES", str(1024 * 1024)))
MAX_WRITE_SIZE_BYTES: int = int(os.environ.get("MAX_WRITE_SIZE_BYTES", str(5 * 1024 * 1024)))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
 
# HTTP transport configuration
MCP_TRANSPORT: str = os.environ.get("MCP_TRANSPORT", "stdio")
MCP_HOST: str = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT: int = int(os.environ.get("MCP_PORT", "8000"))
 
 
def get_api_key() -> str:
    """Retrieve the API key from environment variables.
 
    Returns:
        The API key string.
 
    Raises:
        RuntimeError: If MCP_API_KEY is not set.
    """
    key = os.environ.get("MCP_API_KEY")
    if not key:
        raise RuntimeError("MCP_API_KEY environment variable must be set when transport is HTTP")
    return key

# Directories excluded from search results to reduce noise
SEARCH_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        ".venv_container",
        ".mcp",
        "__pycache__",
        ".git",
        ".ruff_cache",
        ".venv",
    }
)


def safe_path(target_path: str) -> Path:
    """Resolve a path and enforce workspace boundary using CodeQL-friendly patterns.

    Args:
        target_path: Relative or absolute path string.

    Returns:
        Resolved absolute Path guaranteed to be within WORKSPACE_ROOT.

    Raises:
        ValueError: If the resolved path escapes WORKSPACE_ROOT.
    """
    # 1. Get the absolute, canonical version of the root
    root = os.path.realpath(str(WORKSPACE_ROOT))

    # 2. Join target_path with root if it's relative
    if os.path.isabs(target_path):
        candidate = target_path
    else:
        candidate = os.path.join(root, target_path)

    # 3. Normalize the candidate (resolves '..' and symlinks)
    # CodeQL recognizes os.path.realpath as a sanitizer for path-injection
    normalized = os.path.realpath(candidate)

    # 4. Explicit prefix check using string comparison
    # CodeQL recognizes .startswith(root) as a valid boundary check
    if not normalized.startswith(root):
        raise ValueError(
            f"Path '{target_path}' resolves to '{normalized}' which is outside "
            f"the workspace boundary '{root}'. "
            f"Use paths relative to /workspace."
        )
    return Path(normalized)


def validate_glob_pattern(pattern: str) -> None:
    """Enforce security restrictions on glob patterns.

    Args:
        pattern: The glob pattern to validate.

    Raises:
        ValueError: If the pattern contains traversal sequences.
    """
    if ".." in pattern or pattern.startswith("/") or pattern.startswith("~"):
        raise ValueError(
            f"Invalid glob pattern '{pattern}'. Path traversal or absolute paths are not allowed."
        )


def validate_patch_security(patch_content: str) -> None:
    """Inspect unified diff headers for path traversal attempts.

    Args:
        patch_content: The unified diff content.

    Raises:
        ValueError: If any target path in the patch is outside WORKSPACE_ROOT.
    """
    # Simple regex to find path headers in unified diffs
    # Examples: --- a/path/to/file, +++ b/path/to/file, --- /absolute/path
    path_headers = re.findall(r"^(?:---|\+\+\+)\s+(.+)$", patch_content, re.MULTILINE)

    for path_str in path_headers:
        # Strip potential prefixes from 'patch -p1' (a/, b/)
        clean_path = path_str.strip()
        if clean_path.startswith("a/") or clean_path.startswith("b/"):
            clean_path = clean_path[2:]

        # Skip special headers like /dev/null
        if clean_path == "/dev/null":
            continue

        # We don't need to resolve yet, but we must ensure it doesn't try to escape.
        # safe_path will do the heavy lifting.
        try:
            safe_path(clean_path)
        except ValueError as e:
            raise ValueError(f"Security violation in patch header: {str(e)}")


def is_binary(filepath: Path, sample_size: int = 8192) -> bool:
    """Check if a file is binary by looking for null bytes.

    Args:
        filepath: Path to the file.
        sample_size: Number of bytes to read for the check.

    Returns:
        True if the file is likely binary, False otherwise.
    """
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(sample_size)
        return b"\x00" in chunk
    except OSError:
        return False
