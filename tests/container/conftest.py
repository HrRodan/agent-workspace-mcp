"""Shared fixtures for container-level (Docker) tests."""

import json
import asyncio
import pytest
from pathlib import Path
from tests.container.utils import MCPHTTPContainerClient


class MCPContainerClient:
    """JSON-RPC client for the MCP server running in Docker via stdio."""

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.process = None
        self._msg_id = 1

    async def start(self):
        """Start the Docker container and perform the MCP handshake."""
        import os
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        gid = os.getgid() if hasattr(os, "getgid") else 1000
        
        abs_workspace = str(self.workspace_dir.resolve())
        cmd = [
            "docker", "run", "-i", "--rm",
            "--memory=2g", "--cpus=2.0", "--pids-limit=256",
            "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            "--tmpfs", "/tmp:size=512m",
            "--env", "UV_PROJECT_ENVIRONMENT=/workspace/.venv_container",
            "--env", "HOME=/tmp",
            "--env", "UV_CACHE_DIR=/tmp/.uv_cache",
            "--user", f"{uid}:{gid}",
            "-v", f"{abs_workspace}:/workspace",
            "agent-workspace-mcp",
        ]
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
        )
        init_res = await self.call("initialize", {
            "capabilities": {},
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "container-tester", "version": "0.1.0"},
        })
        await self.call("notifications/initialized", {})
        return init_res

    async def stop(self):
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

    async def call(self, method: str, params: dict, timeout: int = 300):
        request = {"jsonrpc": "2.0", "id": self._msg_id, "method": method, "params": params}
        self._msg_id += 1
        self.process.stdin.write((json.dumps(request) + "\n").encode())
        await self.process.stdin.drain()
        if method.startswith("notifications/"):
            return None
        try:
            return await asyncio.wait_for(self._wait_for_response(request["id"]), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Tool call '{method}' timed out after {timeout}s.")

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
        res = await self.call("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
        if res and "result" in res:
            content = res["result"].get("content", [])
            if content:
                return content[0].get("text", "")
        return str(res)


@pytest.fixture
async def mcp_client(tmp_path):
    """Provide an MCP container client connected to a fresh workspace."""
    client = MCPContainerClient(tmp_path)
    await client.start()
    yield client
    await client.stop()


@pytest.fixture
async def mcp_http_client(tmp_path):
    """Provide an MCP HTTP container client."""
    client = MCPHTTPContainerClient(tmp_path)
    await client.start()
    yield client
    await client.stop()
