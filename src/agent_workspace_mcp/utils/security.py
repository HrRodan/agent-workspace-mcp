"""Security and path validation utilities for the Agent Workspace MCP."""

import os
from pathlib import Path

# Workspace root is primarily used when running inside a container.
# For local development/testing, it defaults to the /workspace directory
# but can be overridden by environment variables.
WORKSPACE_ROOT: Path = Path(os.environ.get("WORKSPACE_ROOT", "/workspace")).resolve()

COMMAND_TIMEOUT: int = int(os.environ.get("COMMAND_TIMEOUT", "60"))
MAX_SEARCH_RESULTS: int = int(os.environ.get("MAX_SEARCH_RESULTS", "50"))
MAX_READ_SIZE_BYTES: int = int(os.environ.get("MAX_READ_SIZE_BYTES", str(1024 * 1024)))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

# Directories excluded from search results to reduce noise
SEARCH_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        ".venv_container",
        ".mcp",
        "__pycache__",
        ".git",
        ".ruff_cache",
    }
)


def safe_path(target_path: str) -> Path:
    """Resolve a path and enforce workspace boundary.

    Args:
        target_path: Relative or absolute path string.

    Returns:
        Resolved absolute Path guaranteed to be within WORKSPACE_ROOT.

    Raises:
        ValueError: If the resolved path escapes WORKSPACE_ROOT.
    """
    candidate = Path(target_path)

    # If the path is relative, join it with WORKSPACE_ROOT
    if not candidate.is_absolute():
        candidate = WORKSPACE_ROOT / candidate

    # Resolve the path to handle '..' and symlinks.
    # strict=False allows resolving paths that don't exist yet.
    resolved = candidate.resolve(strict=False)

    # Check if the resolved path is still within WORKSPACE_ROOT.
    # .is_relative_to() handles the prefix check securely.
    if not resolved.is_relative_to(WORKSPACE_ROOT):
        raise ValueError(
            f"Path '{target_path}' resolves to '{resolved}' which is outside "
            f"the workspace boundary '{WORKSPACE_ROOT}'. "
            f"Use paths relative to /workspace."
        )
    return resolved


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
