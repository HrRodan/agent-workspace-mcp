import logging
import sys
import io
import os
from logging.handlers import RotatingFileHandler
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_http_headers
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from agent_workspace_mcp.utils import security
from agent_workspace_mcp.tools import filesystem, execution, editing

from agent_workspace_mcp import __version__

logger = logging.getLogger(__name__)



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


if security.MCP_TRANSPORT == "stdio":
    sys.stdout = StdoutRedirector(sys.stdout)


# Disable FastMCP banner and update checks for faster startup
os.environ["FASTMCP_SHOW_SERVER_BANNER"] = "false"
os.environ["FASTMCP_CHECK_FOR_UPDATES"] = "false"

# Initialize FastMCP server
mcp = FastMCP(
    "Agent Workspace",
    version=__version__,
    instructions=(
        "Sandboxed Linux workspace at /workspace. "
        "read_file before search_and_replace for exact whitespace. "
        "Python: uv only (uv init, uv add, uv run). No python/pip."
    ),
)

# Register tools with explicit annotations for better LLM routing
# Filesystem tools
mcp.tool(annotations=ToolAnnotations(
    title="Read File",
    readOnlyHint=True,
    openWorldHint=False,
))(filesystem.read_file)

mcp.tool(annotations=ToolAnnotations(
    title="Write File",
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
))(filesystem.write_file)

mcp.tool(annotations=ToolAnnotations(
    title="List Directory",
    readOnlyHint=True,
    openWorldHint=False,
))(filesystem.list_directory)

mcp.tool(annotations=ToolAnnotations(
    title="Search Workspace",
    readOnlyHint=True,
    openWorldHint=False,
))(filesystem.search_workspace)

# Execution tools
mcp.tool(annotations=ToolAnnotations(
    title="Run Shell Command",
    destructiveHint=True,
    openWorldHint=True,
))(execution.run_bash)

# Editing tools
mcp.tool(annotations=ToolAnnotations(
    title="Search and Replace",
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
))(editing.search_and_replace)



class BearerAuthMiddleware(Middleware):
    """Enforces Bearer token authentication for all tool calls in HTTP mode."""
    def __init__(self, token: str):
        self.token = token

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        headers = get_http_headers() or {}
        # Uvicorn and fastmcp lowercase all headers
        auth_header = headers.get("authorization", "")
        
        if not auth_header.startswith("Bearer ") or auth_header[7:] != self.token:
            raise ToolError("Unauthorized: Invalid or missing API key")
            
        return await call_next(context)


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
    
    logger.info("Agent Workspace MCP server starting (transport=%s)...", security.MCP_TRANSPORT)
    logger.info("Workspace root: %s", security.WORKSPACE_ROOT)
    logger.info("Log level: %s", security.LOG_LEVEL)

    if security.MCP_TRANSPORT == "http":
        import uvicorn
        from starlette.middleware.base import BaseHTTPMiddleware
        from fastapi.responses import JSONResponse
        
        from starlette.applications import Starlette
        from starlette.routing import Mount
        from starlette.middleware import Middleware
        
        api_key = security.get_api_key()
        mcp_app = mcp.http_app(transport='sse')
        
        class AuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                auth_header = request.headers.get("Authorization")
                print(f"DEBUG STARLETTE AUTH: path={request.url.path} auth={auth_header}", flush=True)
                
                if not auth_header or auth_header != f"Bearer {api_key}":
                    print(f"DEBUG STARLETTE AUTH: DENIED path={request.url.path}", flush=True)
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Unauthorized: Invalid or missing API key"}
                    )
                return await call_next(request)
        
        # Create a wrapper app to ensure middleware is applied correctly
        final_app = Starlette(
            routes=[Mount("/", app=mcp_app)],
            middleware=[Middleware(AuthMiddleware)]
        )
        
        # Disable FastMCP banner and update checks for faster startup
        os.environ["FASTMCP_SHOW_SERVER_BANNER"] = "false"
        os.environ["FASTMCP_CHECK_FOR_UPDATES"] = "false"
        
        logger.info("HTTP endpoint: http://%s:%d/sse", security.MCP_HOST, security.MCP_PORT)
        uvicorn.run(final_app, host=security.MCP_HOST, port=security.MCP_PORT, log_level="info")
    else:
        # Default stdio transport
        mcp.run()


if __name__ == "__main__":
    main()
