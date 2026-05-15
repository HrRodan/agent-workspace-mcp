import asyncio
import os
import subprocess
from pathlib import Path

class MCPHTTPContainerClient:
    """Client for the MCP server running in Docker via HTTP."""

    def __init__(self, workspace_dir: Path, api_key: str = "test-key"):
        self.workspace_dir = workspace_dir
        self.api_key = api_key
        self.container_id = None
        self.host_port = None
        self._msg_id = 1

    async def start(self):
        """Start the Docker container in HTTP mode."""
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        gid = os.getgid() if hasattr(os, "getgid") else 1000
        
        abs_workspace = str(self.workspace_dir.resolve())
        cmd = [
            "docker", "run", "-d", "--rm",
            "--memory=2g", "--cpus=2.0", "--pids-limit=256",
            "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            "-p", "127.0.0.1:0:8000",
            "--env", "MCP_TRANSPORT=http",
            "--env", "MCP_API_KEY=" + self.api_key,
            "--user", f"{uid}:{gid}",
            "-v", f"{abs_workspace}:/workspace",
            "agent-workspace-mcp",
        ]
        
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        self.container_id = res.stdout.strip()
        
        res = subprocess.run(["docker", "port", self.container_id, "8000/tcp"], capture_output=True, text=True, check=True)
        first_line = res.stdout.strip().split("\n")[0]
        self.host_port = first_line.split(":")[-1]
        
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < 15:
            log_res = subprocess.run(["docker", "logs", self.container_id], capture_output=True, text=True)
            if "Uvicorn running on" in log_res.stdout or "Uvicorn running on" in log_res.stderr:
                break
            await asyncio.sleep(0.1)
        else:
            log_res = subprocess.run(["docker", "logs", self.container_id], capture_output=True, text=True)
            raise TimeoutError(
                f"MCP HTTP server failed to start within 15s. Container logs:\n{log_res.stdout}\n{log_res.stderr}"
            )

    async def stop(self):
        if self.container_id:
            subprocess.run(["docker", "stop", self.container_id], capture_output=True)

    async def run_tool(self, name: str, arguments: dict):
        from fastmcp.client import Client
        from fastmcp.client.transports import SSETransport
        
        # We use /sse which is the standard FastMCP endpoint
        transport = SSETransport(
            f"http://127.0.0.1:{self.host_port}/sse",
            auth=self.api_key
        )
        
        try:
            async with Client(transport) as client:
                result = await client.call_tool(name, arguments)
                if result and hasattr(result, "content") and result.content:
                    return result.content[0].text
                return str(result)
        except Exception as e:
            return f"Error: {e}"

    async def call(self, method: str, params: dict, headers: dict = None):
        """Low-level call for testing specific scenarios like auth failure."""
        import httpx
        if headers is None:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json, text/event-stream"
            }
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(
                f"http://127.0.0.1:{self.host_port}/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "id": self._msg_id,
                    "method": method,
                    "params": params
                },
                headers=headers,
                timeout=30.0
            )
            self._msg_id += 1
            return resp
