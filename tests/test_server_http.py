import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Mocking security before importing server to avoid top-level side effects if needed,
# though we handle it with patch.dict(os.environ) usually.

@patch("agent_workspace_mcp.server.mcp.run")
def test_main_defaults_to_stdio(mock_run):
    with patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"}):
        # Reloading or just calling main if it hasn't cached transport
        from agent_workspace_mcp.server import main
        main()
        mock_run.assert_called_once_with()

@patch("agent_workspace_mcp.server.mcp.run")
def test_main_http_transport(mock_run):
    with patch.dict(os.environ, {"MCP_TRANSPORT": "http", "MCP_API_KEY": "test-key", "MCP_HOST": "1.2.3.4", "MCP_PORT": "9999"}):
        # We need to ensure security module picks up the new env vars
        from agent_workspace_mcp.utils import security
        import importlib
        importlib.reload(security)
        
        from agent_workspace_mcp.server import main
        main()
        mock_run.assert_called_once_with(transport="streamable-http", host="1.2.3.4", port=9999)

def test_main_http_requires_api_key():
    with patch.dict(os.environ, {"MCP_TRANSPORT": "http"}, clear=True):
        from agent_workspace_mcp.utils import security
        import importlib
        importlib.reload(security)
        
        from agent_workspace_mcp.server import main
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

@pytest.mark.asyncio
async def test_bearer_auth_middleware_valid():
    from agent_workspace_mcp.server import BearerAuthMiddleware
    from fastmcp.server.middleware import MiddlewareContext
    
    middleware = BearerAuthMiddleware("secret123")
    context = MagicMock(spec=MiddlewareContext)
    call_next = AsyncMock()
    
    with patch("agent_workspace_mcp.server.get_http_headers", return_value={"authorization": "Bearer secret123"}):
        await middleware.on_call_tool(context, call_next)
        call_next.assert_called_once_with(context)

@pytest.mark.asyncio
async def test_bearer_auth_middleware_invalid():
    from agent_workspace_mcp.server import BearerAuthMiddleware
    from fastmcp.exceptions import ToolError
    
    middleware = BearerAuthMiddleware("secret123")
    context = MagicMock()
    call_next = AsyncMock()
    
    # Case 1: Wrong token
    with patch("agent_workspace_mcp.server.get_http_headers", return_value={"authorization": "Bearer wrong"}):
        with pytest.raises(ToolError, match="Unauthorized"):
            await middleware.on_call_tool(context, call_next)
            
    # Case 2: Missing Bearer prefix
    with patch("agent_workspace_mcp.server.get_http_headers", return_value={"authorization": "secret123"}):
        with pytest.raises(ToolError, match="Unauthorized"):
            await middleware.on_call_tool(context, call_next)

    # Case 3: Missing header
    with patch("agent_workspace_mcp.server.get_http_headers", return_value={}):
        with pytest.raises(ToolError, match="Unauthorized"):
            await middleware.on_call_tool(context, call_next)
