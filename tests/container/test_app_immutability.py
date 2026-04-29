"""Container tests: /app directory is immutable for the runtime user."""
import pytest


@pytest.mark.asyncio
async def test_cannot_create_file_in_app(mcp_client):
    """Creating a file in /app must fail with permission denied."""
    output = await mcp_client.run_tool("run_bash", {"command": "touch /app/evil.txt 2>&1"})
    assert "Permission denied" in output or "Read-only" in output


@pytest.mark.asyncio
async def test_cannot_modify_server_source(mcp_client):
    """Appending to server.py must fail."""
    output = await mcp_client.run_tool(
        "run_bash",
        {"command": "echo 'hacked' >> /app/src/agent_workspace_mcp/server.py 2>&1"},
    )
    assert "Permission denied" in output or "Read-only" in output


@pytest.mark.asyncio
async def test_cannot_modify_security_module(mcp_client):
    """sed -i on security.py must fail."""
    output = await mcp_client.run_tool(
        "run_bash",
        {"command": "sed -i 's/raise/pass/' /app/src/agent_workspace_mcp/utils/security.py 2>&1"},
    )
    assert "Permission denied" in output or "Read-only" in output or "couldn't open" in output.lower()


@pytest.mark.asyncio
async def test_cannot_delete_venv(mcp_client):
    """Deleting the server venv must fail."""
    # Limit output to avoid exceeding test client line length limits
    output = await mcp_client.run_tool("run_bash", {"command": "rm -rf /app/.venv 2>&1 | head -n 20"})
    assert "Permission denied" in output or "Read-only" in output


@pytest.mark.asyncio
async def test_server_functional_after_tamper_attempts(mcp_client):
    """After all tamper attempts, the server still lists tools correctly."""
    # Run a benign tamper attempt first
    await mcp_client.run_tool("run_bash", {"command": "touch /app/evil.txt 2>&1"})
    # Then verify the server is still working
    res = await mcp_client.call("tools/list", {})
    tool_names = {t["name"] for t in res["result"]["tools"]}
    assert "run_bash" in tool_names
    assert "read_file" in tool_names


@pytest.mark.asyncio
async def test_procps_removed(mcp_client):
    """Verify that procps tools like pgrep are not available."""
    output = await mcp_client.run_tool("run_bash", {"command": "which pgrep 2>&1 || echo 'not found'"})
    assert "not found" in output
