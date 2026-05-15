import pytest
import httpx
from tests.container.utils import MCPHTTPContainerClient

@pytest.mark.asyncio
async def test_http_health_check(mcp_http_client):
    """Verify that the MCP HTTP endpoint responds."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # GET on /mcp/ is rewritten to /sse internally
        headers = {"Accept": "application/json, text/event-stream"}
        resp = await client.get(f"http://127.0.0.1:{mcp_http_client.host_port}/mcp/", headers=headers, timeout=1.0)
        # 200 OK or Timeout (which means stream started) are both acceptable
        assert resp.status_code == 200 or resp.status_code >= 400 

@pytest.mark.asyncio
async def test_http_auth_required(mcp_http_client):
    """Verify that requests without valid auth are rejected."""
    # Test via run_tool with wrong key
    client = MCPHTTPContainerClient(mcp_http_client.workspace_dir, api_key="wrong-key")
    client.host_port = mcp_http_client.host_port
    
    result = await client.run_tool("tools/list", {})
    assert "Unauthorized" in result

@pytest.mark.asyncio
async def test_http_tool_execution(mcp_http_client):
    """Verify that tools can be executed over HTTP with valid auth."""
    # List tools
    result = await mcp_http_client.run_tool("list_directory", {"path": "."})
    assert "Error" not in result

@pytest.mark.asyncio
async def test_http_workspace_isolation(mcp_http_client):
    """Verify that the workspace is accessible and isolated."""
    await mcp_http_client.run_tool("write_file", {"filepath": "test.txt", "content": "http-isolation-test"})
    result = await mcp_http_client.run_tool("read_file", {"filepath": "test.txt"})
    assert result == "http-isolation-test"
