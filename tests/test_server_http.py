import os
import pytest
from unittest.mock import patch

# Mocking security before importing server to avoid top-level side effects if needed,
# though we handle it with patch.dict(os.environ) usually.

@patch("agent_workspace_mcp.server.mcp.run")
def test_main_defaults_to_stdio(mock_run):
    with patch.dict(os.environ, {"MCP_TRANSPORT": "stdio"}):
        # Reloading or just calling main if it hasn't cached transport
        from agent_workspace_mcp.server import main
        main()
        mock_run.assert_called_once_with()

@patch("uvicorn.run")
@patch("agent_workspace_mcp.server.mcp.run")
def test_main_http_transport(mock_mcp_run, mock_uvicorn_run):
    with patch.dict(os.environ, {"MCP_TRANSPORT": "http", "MCP_API_KEY": "test-key", "MCP_HOST": "1.2.3.4", "MCP_PORT": "9999"}):
        # We need to ensure security module picks up the new env vars
        from agent_workspace_mcp.utils import security
        import importlib
        importlib.reload(security)
        
        from agent_workspace_mcp.server import main
        main()
        mock_uvicorn_run.assert_called_once()
        args, kwargs = mock_uvicorn_run.call_args
        assert kwargs.get("host") == "1.2.3.4"
        assert kwargs.get("port") == 9999
        mock_mcp_run.assert_not_called()
        
        # Test the Starlette app directly using TestClient to verify the global AuthMiddleware
        app = args[0]
        from starlette.testclient import TestClient
        client = TestClient(app)
        
        # 1. Unauthenticated request should be rejected with 401
        resp = client.get("/invalid-path-for-testing")
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Unauthorized: Invalid or missing API key"}
        
        # 2. Authenticated request should bypass AuthMiddleware and proceed to Starlette's router (returning 404)
        resp = client.get("/invalid-path-for-testing", headers={"Authorization": "Bearer test-key"})
        assert resp.status_code == 404

def test_main_http_requires_api_key():
    with patch.dict(os.environ, {"MCP_TRANSPORT": "http"}, clear=True):
        from agent_workspace_mcp.utils import security
        import importlib
        importlib.reload(security)
        
        from agent_workspace_mcp.server import main
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1
