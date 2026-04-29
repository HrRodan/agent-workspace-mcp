"""Test MCP protocol handshake and tool discovery."""
import pytest

@pytest.mark.asyncio
async def test_initialize_returns_capabilities(mcp_client):
    """The initialize handshake already happened in the fixture; verify tool listing."""
    res = await mcp_client.call("tools/list", {})
    tool_names = {t["name"] for t in res["result"]["tools"]}
    expected = {"read_file", "write_file", "list_directory", "search_workspace",
                "run_bash", "search_and_replace"}
    assert expected == tool_names
