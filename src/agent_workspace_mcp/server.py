import logging
import sys
from logging.handlers import RotatingFileHandler
from fastmcp import FastMCP

from agent_workspace_mcp.utils import security
from agent_workspace_mcp.tools import filesystem, execution, editing

# Initialize FastMCP server
mcp = FastMCP(
    "Agent Workspace MCP",
    instructions=(
        "You are operating inside a sandboxed Linux workspace at /workspace. "
        "Always use read_file before search_and_replace to ensure exact whitespace matching. "
        "For new projects, use run_bash('uv init') then uv add for dependencies. "
        "For single scripts, use PEP 723 inline metadata with uv run."
    ),
)

# Register tools explicitly
# Filesystem tools
mcp.add_tool(filesystem.read_file)
mcp.add_tool(filesystem.write_file)
mcp.add_tool(filesystem.list_directory)
mcp.add_tool(filesystem.get_file_info)
mcp.add_tool(filesystem.search_workspace)

# Execution tools
mcp.add_tool(execution.run_bash)
mcp.add_tool(execution.lint_workspace)

# Editing tools
mcp.add_tool(editing.apply_patch)
mcp.add_tool(editing.search_and_replace)


def setup_logging() -> None:
    """Configure dual logging: stderr + rotating file in /workspace/.mcp/."""
    log_dir = security.WORKSPACE_ROOT / ".mcp"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        # If /workspace is read-only and .mcp doesn't exist, log to stderr only
        pass

    log_file = log_dir / "server.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Stderr handler (safe for stdio servers as long as it's stderr, not stdout)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_log_level = getattr(logging, security.LOG_LEVEL, logging.INFO)
    root_logger.setLevel(root_log_level)
    root_logger.addHandler(stderr_handler)

    # Rotating file handler (5MB, 2 backups) if writable
    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=2,
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception:
        root_logger.warning(
            "Could not create log file at %s, logging to stderr only", log_file
        )


def main() -> None:
    """Entry point for the Agent Workspace MCP server."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Agent Workspace MCP server starting...")
    logger.info("Workspace root: %s", security.WORKSPACE_ROOT)

    # Run the server using stdio transport
    mcp.run()


if __name__ == "__main__":
    main()
