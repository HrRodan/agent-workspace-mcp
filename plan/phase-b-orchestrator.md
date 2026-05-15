# Phase B: Multi-Tenant Orchestrator

This document outlines the architecture and implementation strategy for **Phase B**, which introduces a multi-tenant Orchestrator. 

Because the Agent Workspace MCP server operates directly on the host's OS resources (filesystem, processes) via the `run_bash` and `write_file` tools, a single HTTP server cannot safely serve multiple independent agents. Phase B solves this by introducing a lightweight API Gateway that spins up an isolated, ephemeral Docker container for each client session.

---

## 1. Architecture Overview

```mermaid
flowchart TD
    ClientA["Agent A"] -- "HTTP (API Key)" --> Orch["Orchestrator (FastAPI)"]
    ClientB["Agent B"] -- "HTTP (API Key)" --> Orch

    subgraph HostSystem ["Host Machine"]
        Orch -- "Docker API\nCreate Container" --> DockerDaemon["Docker Engine"]
        
        subgraph SessionA ["Session A"]
            Orch -- "Proxy requests" --> ContA["Container A\n(Port 8001)\n/workspace-a"]
        end
        
        subgraph SessionB ["Session B"]
            Orch -- "Proxy requests" --> ContB["Container B\n(Port 8002)\n/workspace-b"]
        end
    end
```

### Core Principles
1. **Physical Isolation:** Every session gets its own container, guaranteeing that Agent A cannot see or interfere with Agent B's files, processes, or environment variables.
2. **Ephemeral Workspaces:** Workspaces are temporary and destroyed when the session ends.
3. **No Changes to MCP Server:** The `agent-workspace-mcp` Docker image built in Phase A remains exactly the same. The orchestrator simply orchestrates the containers.

---

## 2. Components to Build

The Orchestrator will be a new Python service (e.g., in a `services/orchestrator` directory or a separate repo), built using:
- **FastAPI**: For the HTTP API and routing.
- **Docker SDK for Python (`docker`)**: To manage container lifecycles.
- **httpx**: To proxy JSON-RPC requests to the underlying containers.

### 2.1 API Endpoints

1. **`POST /api/sessions`**
   - **Purpose:** Initialize a new session.
   - **Action:** Generates a unique `session_id`, creates an ephemeral directory on the host, and starts a new `agent-workspace-mcp` container binding that directory to `/workspace`.
   - **Response:** Returns the `session_id`.

2. **`POST /mcp/{session_id}`**
   - **Purpose:** The actual MCP JSON-RPC endpoint.
   - **Action:** Looks up the container port associated with `session_id` and proxies the HTTP request to the container.

3. **`DELETE /api/sessions/{session_id}`**
   - **Purpose:** Terminate a session early.
   - **Action:** Stops/kills the container and deletes the host workspace directory.

### 2.2 The Container Spawner

When creating a session, the Orchestrator uses the Docker SDK to run a container:

```python
import docker
import uuid
import tempfile

client = docker.from_env()

def spawn_container(session_id: str):
    # 1. Create an ephemeral workspace directory on the host
    workspace_dir = tempfile.mkdtemp(prefix=f"mcp-workspace-{session_id}-")
    
    # 2. Start the container in HTTP mode
    container = client.containers.run(
        image="ghcr.io/hrrodan/agent-workspace-mcp:latest",
        detach=True,
        remove=True,  # Auto-cleanup on exit
        init=True,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        mem_limit="2g",
        cpu_quota=200000,
        pids_limit=256,
        user="1000:1000",
        tmpfs={"/tmp": "size=64m", "/home/mcpuser/.cache": "size=512m"},
        volumes={workspace_dir: {"bind": "/workspace", "mode": "rw"}},
        ports={"8000/tcp": None}, # Let Docker assign a random ephemeral host port
        environment={
            "MCP_TRANSPORT": "http",
            "MCP_API_KEY": "internal-orchestrator-key" # Only the orchestrator knows this
        }
    )
    
    # 3. Get the randomly assigned host port
    container.reload()
    port = container.ports["8000/tcp"][0]["HostPort"]
    
    return {"container_id": container.id, "port": port, "workspace_dir": workspace_dir}
```

### 2.3 The Proxy Router

The FastAPI route simply forwards the request. FastMCP uses HTTP POST for JSON-RPC messages.

```python
import httpx
from fastapi import Request

@app.post("/mcp/{session_id}")
async def proxy_mcp(session_id: str, request: Request):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Forward to the specific container's assigned port
    target_url = f"http://127.0.0.1:{session['port']}/mcp/"
    
    async with httpx.AsyncClient() as client:
        # Pass the orchestrator's internal API key to satisfy Phase A auth
        headers = {"Authorization": "Bearer internal-orchestrator-key"}
        body = await request.body()
        
        response = await client.post(target_url, content=body, headers=headers)
        
        return Response(content=response.content, status_code=response.status_code)
```

### 2.4 The Garbage Collector (Reaper)

To prevent resource leaks from abandoned sessions (e.g., if an agent disconnects unexpectedly), a background task must run periodically:

1. Scan all active sessions.
2. Check the "last accessed" timestamp (updated on every proxy request).
3. If inactivity > 30 minutes, invoke `DELETE /api/sessions/{session_id}` to kill the container and delete the workspace.

---

## 3. Security Considerations

1. **Docker Socket Access:** The Orchestrator requires access to `/var/run/docker.sock` to spawn containers. This makes the Orchestrator highly privileged. It should be heavily locked down.
2. **Orchestrator Auth:** The Orchestrator itself needs an API Key system so external agents can authenticate before calling `/api/sessions`.
3. **Internal Auth:** The Orchestrator and the spawned containers communicate over `localhost`. They should use a shared, randomly generated internal `MCP_API_KEY` (configured in Phase A) to prevent direct access to the container ports from other users on the host.

---

## 4. Implementation Steps (When Ready)

1. Create a `services/orchestrator` directory.
2. Initialize a new `uv` project with `fastapi`, `uvicorn`, `docker`, and `httpx`.
3. Implement `main.py` with the lifecycle and proxy routes.
4. Implement `reaper.py` as an `asyncio` background task.
5. Create a `Dockerfile` for the Orchestrator.
6. Write a `docker-compose.yml` that deploys the Orchestrator with the Docker socket mounted, ensuring it can pull the `agent-workspace-mcp` image.
