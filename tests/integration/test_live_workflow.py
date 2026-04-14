import os
import json
import asyncio
import pytest
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Skip tests if no API key is available
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not found in environment",
)

DEFAULT_MODEL = os.environ.get(
    "DEFAULT_MODEL", "openrouter/google/gemini-3-flash-preview"
)


class MCPContainerClient:
    """A simple client to interact with the MCP server running in Docker."""

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.process = None
        self._msg_id = 1

    async def start(self):
        """Start the Docker container and connect to its stdio."""
        # Use absolute path for volume mount
        abs_workspace = str(self.workspace_dir.resolve())

        # Build docker run command
        cmd = [
            "docker",
            "run",
            "-i",
            "--rm",
            "--memory=2g",
            "--cpus=2.0",
            "--pids-limit=256",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--tmpfs",
            "/tmp:size=64m",
            "--tmpfs",
            "/home/mcpuser/.cache:size=512m",
            "--env",
            "UV_PROJECT_ENVIRONMENT=/workspace/.venv_container",
            "--user",
            "1000:1000",
            "-v",
            f"{abs_workspace}:/workspace",
            "agent-workspace-mcp",
        ]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
        )

        # Initial handshake
        init_res = await self.call(
            "initialize",
            {
                "capabilities": {},
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "e2e-tester", "version": "0.1.0"},
            },
        )
        await self.call("notifications/initialized", {})
        return init_res

    async def stop(self):
        """Stop the container."""
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

    async def call(self, method: str, params: dict, timeout: int = 300):
        """Perform a JSON-RPC call."""
        request = {
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": method,
            "params": params,
        }
        self._msg_id += 1

        msg = json.dumps(request) + "\n"
        self.process.stdin.write(msg.encode())
        await self.process.stdin.drain()

        if method.startswith("notifications/"):
            return None

        # Read lines until we get a response, with a timeout to prevent hanging forever
        try:
            return await asyncio.wait_for(self._wait_for_response(request["id"]), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Handshake or tool call '{method}' timed out after {timeout}s.")

    async def _wait_for_response(self, request_id: int):
        while True:
            line = await self.process.stdout.readline()
            if not line:
                return None
            try:
                response = json.loads(line.decode())
                if "id" in response and response["id"] == request_id:
                    return response
            except json.JSONDecodeError:
                continue

    async def run_tool(self, name: str, arguments: dict, timeout: int = 300):
        """Call a tool on the MCP server."""
        res = await self.call("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
        if res and "result" in res:
            content = res["result"].get("content", [])
            if content:
                return content[0].get("text", "")
        return str(res)


@pytest.mark.asyncio
async def test_workflow_pep723_script(tmp_path):
    """Scenario 1: Agent creates a PEP 723 script and runs it using an included package (standard library)."""
    client = MCPContainerClient(tmp_path)
    try:
        await client.start()

        # 1. Write the script using 'json' (standard library, no download needed)
        script_content = """# /// script
# dependencies = []
# ///
import json
print(json.dumps({"status": "ok"}))
"""
        await client.run_tool(
            "write_file", {"filepath": "hello.py", "content": script_content}
        )

        # 2. Run the script with uv run
        output = await client.run_tool("run_bash", {"command": "uv run hello.py"})

        assert '{"status": "ok"}' in output

    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_workflow_download_requests(tmp_path):
    """Scenario: Agent downloads a package (requests) from PyPI."""
    client = MCPContainerClient(tmp_path)
    try:
        await client.start()

        # 1. Write the script
        script_content = """# /// script
# dependencies = ["requests"]
# ///
import requests
print("downloaded requests")
"""
        await client.run_tool(
            "write_file", {"filepath": "download.py", "content": script_content}
        )

        # 2. Run the script with uv run - give it 300s to download
        output = await client.run_tool(
            "run_bash", 
            {"command": "uv run download.py", "timeout": 300},
            timeout=310
        )

        assert "downloaded requests" in output

    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_workflow_project_bootstrap(tmp_path):
    """Scenario 2: Agent inits a project, adds dependencies, and runs it."""
    client = MCPContainerClient(tmp_path)
    try:
        await client.start()

        # 1. uv init
        await client.run_tool(
            "run_bash", {"command": "uv init --name myproject --no-readme"}
        )

        # 2. Update hello.py
        await client.run_tool(
            "write_file", {"filepath": "hello.py", "content": "print('bootstrapped')"}
        )

        # 3. run
        output = await client.run_tool("run_bash", {"command": "uv run hello.py"})
        assert "bootstrapped" in output

    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_security_boundary(tmp_path):
    """Scenario 5: Agent attempts to read /etc/passwd — must fail."""
    client = MCPContainerClient(tmp_path)
    try:
        await client.start()

        output = await client.run_tool("read_file", {"filepath": "/etc/passwd"})
        assert "outside the workspace boundary" in output

    finally:
        await client.stop()


