"""Container-level security boundary tests."""
import pytest

@pytest.mark.asyncio
async def test_read_outside_workspace_blocked(mcp_client):
    """Attempting to read /etc/passwd must be rejected by the server."""
    output = await mcp_client.run_tool("read_file", {"filepath": "/etc/passwd"})
    assert "outside the workspace boundary" in output

@pytest.mark.asyncio
async def test_no_setuid_binaries(mcp_client):
    """Verify that CIS Benchmark 4.8 is applied: no setuid/setgid binaries exist in the container."""
    output = await mcp_client.run_tool("run_bash", {"command": "find / -xdev \\( -perm -4000 -o -perm -2000 \\) 2>/dev/null"})
    # The output should be empty because no such files exist
    # If find encounters permission denied on directories, it exits with 1, which the tool prints as '[Exit code: 1]'
    clean_output = output.replace("[Exit code: 1]", "").strip()
    assert clean_output == "", f"Found setuid/setgid binaries: {clean_output}"
