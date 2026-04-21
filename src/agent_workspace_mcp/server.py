import logging
import sys
import io
from logging.handlers import RotatingFileHandler
from fastmcp import FastMCP

from agent_workspace_mcp.utils import security
from agent_workspace_mcp.tools import filesystem, execution, editing


# Redirect stdout to stderr to prevent any accidental prints from corrupting the JSON-RPC stream.
# FastMCP/MCP servers communicate over stdout.buffer; text prints go to sys.stdout.write.
class StdoutRedirector(io.TextIOBase):
    def __init__(self, real_stdout):
        self.real_stdout = real_stdout

    @property
    def buffer(self):
        # FastMCP and the MCP SDK use sys.stdout.buffer for raw JSON-RPC bytes.
        return self.real_stdout.buffer

    def write(self, s):
        # Accidental prints to sys.stdout are redirected to sys.stderr.
        return sys.stderr.write(s)

    def flush(self):
        return sys.stderr.flush()


sys.stdout = StdoutRedirector(sys.stdout)


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
mcp.tool(annotations={"readOnlyHint": True})(filesystem.read_file)
mcp.tool(annotations={"destructiveHint": True, "idempotentHint": True})(filesystem.write_file)
mcp.tool(annotations={"readOnlyHint": True})(filesystem.list_directory)
mcp.tool(annotations={"readOnlyHint": True})(filesystem.search_workspace)

# Execution tools
mcp.tool()(execution.run_bash)

# Editing tools
mcp.tool(annotations={"destructiveHint": True})(editing.search_and_replace)


def setup_logging() -> None:
    """Configure dual logging: stderr + rotating file in /workspace/.mcp/."""
    try:
        log_dir = security.safe_path(".mcp")
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        # If /workspace is read-only and .mcp doesn't exist, log to stderr only
        # We define a fallback log_dir to avoid UnboundLocalError
        log_dir = security.WORKSPACE_ROOT / ".mcp"
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
    logger.info("Log level: %s", security.LOG_LEVEL)

    # Run the server using stdio transport
    mcp.run()


if __name__ == "__main__":
    main()
