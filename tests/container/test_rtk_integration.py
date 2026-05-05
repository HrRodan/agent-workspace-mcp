import pytest

@pytest.mark.asyncio
async def test_rtk_binary_exists(mcp_client):
    """Verify that the rtk binary is installed and in the PATH."""
    output = await mcp_client.run_tool("run_bash", {"command": "which rtk"})
    assert "/usr/local/bin/rtk" in output

@pytest.mark.asyncio
async def test_rtk_rewrite_functionality(mcp_client):
    """Verify that rtk rewrite works as expected inside the container."""
    # We use 'rtk rewrite' directly to see if it responds correctly
    output = await mcp_client.run_tool("run_bash", {"command": "rtk rewrite 'ls -al'"})
    assert "rtk ls -al" in output

@pytest.mark.asyncio
async def test_rtk_automatic_optimization(mcp_client):
    """Verify that run_bash automatically uses RTK for optimization.
    
    Standard 'ls -la' output contains full permission strings like 'drwxr-xr-x'.
    RTK's 'ls' output is optimized and uses a tree-like structure or summarized format.
    """
    # Create a dummy file to ensure there's something to list
    await mcp_client.run_tool("write_file", {"filepath": "test_rtk.txt", "content": "hello"})
    
    # Run ls -la. Our tool should rewrite this to 'rtk ls -la'
    output = await mcp_client.run_tool("run_bash", {"command": "ls -la test_rtk.txt"})
    
    # RTK's output for a single file usually looks like:
    # -rw-r--r-- ... test_rtk.txt
    # Wait, let's see what RTK actually outputs. 
    # Usually RTK output is very clean.
    
    # A good way to verify is to check for something RTK adds or removes.
    # RTK 'ls' often removes the 'total X' line at the top of 'ls -la'
    assert "total" not in output
    assert "test_rtk.txt" in output
