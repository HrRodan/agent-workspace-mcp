"""Container-level security boundary tests."""
import pytest

@pytest.mark.asyncio
async def test_read_outside_workspace_blocked(mcp_client):
    """Attempting to read /etc/passwd must be rejected by the server."""
    output = await mcp_client.run_tool("read_file", {"filepath": "/etc/passwd"})
    assert "outside the workspace boundary" in output
