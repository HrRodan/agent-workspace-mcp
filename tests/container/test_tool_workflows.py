"""Tool workflow tests in a real container environment."""
import pytest

@pytest.mark.asyncio
async def test_workflow_pep723_script(mcp_client):
    """Scenario 1: Agent creates a PEP 723 script and runs it using an included package (standard library)."""
    # 1. Write the script using 'json' (standard library, no download needed)
    script_content = """# /// script
# dependencies = []
# ///
import json
print(json.dumps({"status": "ok"}))
"""
    await mcp_client.run_tool(
        "write_file", {"filepath": "hello.py", "content": script_content}
    )

    # 2. Run the script with uv run
    output = await mcp_client.run_tool("run_bash", {"command": "uv run hello.py"})

    assert '{"status": "ok"}' in output


@pytest.mark.asyncio
async def test_workflow_download_requests(mcp_client):
    """Scenario: Agent downloads a package (requests) from PyPI."""
    # 1. Write the script
    script_content = """# /// script
# dependencies = ["requests"]
# ///
import requests
print("downloaded requests")
"""
    await mcp_client.run_tool(
        "write_file", {"filepath": "download.py", "content": script_content}
    )

    # 2. Run the script with uv run - give it 120s to download in CI
    output = await mcp_client.run_tool(
        "run_bash", 
        {"command": "uv run download.py", "timeout": 120},
        timeout=130
    )

    assert "downloaded requests" in output


@pytest.mark.asyncio
async def test_workflow_project_bootstrap(mcp_client):
    """Scenario 2: Agent inits a project, adds dependencies, and runs it."""
    # 1. uv init
    await mcp_client.run_tool(
        "run_bash", {"command": "uv init --name myproject --no-readme"}
    )

    # 2. Update hello.py
    await mcp_client.run_tool(
        "write_file", {"filepath": "hello.py", "content": "print('bootstrapped')"}
    )

    # 3. run
    output = await mcp_client.run_tool("run_bash", {"command": "uv run hello.py"})
    assert "bootstrapped" in output
