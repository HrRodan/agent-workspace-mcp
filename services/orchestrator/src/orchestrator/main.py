import asyncio
import time
import uuid
import logging
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Depends, Request, HTTPException, Response
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from orchestrator.config import settings
from orchestrator.spawner import spawn_container, terminate_container, SpawnerError
from orchestrator.reaper import sessions, session_reaper_loop

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("orchestrator.main")

# Setup auth bearer
security = HTTPBearer()

def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verifies that the incoming client Bearer token matches the Orchestrator API key."""
    if credentials.credentials != settings.orchestrator_api_key:
        raise HTTPException(status_code=401, detail="Invalid Orchestrator API Key")
    return credentials.credentials

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start session reaper background loop
    reaper_task = asyncio.create_task(session_reaper_loop(interval_seconds=15))
    yield
    # Shutdown: Cancel reaper background task
    logger.info("Orchestrator shutting down, cancelling reaper background task...")
    reaper_task.cancel()
    try:
        await reaper_task
    except asyncio.CancelledError:
        pass
        
    # Clean up all spawned container sessions to avoid orphans on shutdown
    logger.info("Cleaning up all active agent container sessions...")
    active_sessions = list(sessions.items())
    for session_id, session in active_sessions:
        logger.info("Pruning active session %s during shutdown...", session_id)
        try:
            terminate_container(session["container_name"], session["workspace_dir"])
        except Exception as e:
            logger.error("Failed to terminate container %s: %s", session["container_name"], str(e))
    sessions.clear()

# Initialize FastAPI application
app = FastAPI(
    title="MCP Multi-Tenant Orchestrator",
    version="0.1.0",
    lifespan=lifespan
)

@app.get("/health")
def health():
    """Unauthenticated health endpoint for load balancers or orchestrators."""
    return {"status": "ok", "sessions_active": len(sessions)}

@app.post("/api/sessions", dependencies=[Depends(verify_api_key)])
def create_session():
    """Spawns a new isolated agent container session."""
    session_id = uuid.uuid4().hex
    try:
        session_info = spawn_container(session_id)
    except SpawnerError as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    # Register session
    sessions[session_id] = {
        "container_name": session_info["container_name"],
        "workspace_dir": session_info["workspace_dir"],
        "target_url": session_info["target_url"],
        "internal_key": session_info["internal_key"],
        "last_accessed": time.time()
    }
    
    return {"session_id": session_id}

@app.get("/api/sessions", dependencies=[Depends(verify_api_key)])
def list_sessions():
    """Lists metadata for all active sessions."""
    now = time.time()
    result = []
    for sid, data in sessions.items():
        result.append({
            "session_id": sid,
            "container_name": data["container_name"],
            "target_url": data["target_url"],
            "last_accessed": data["last_accessed"],
            "idle_seconds": int(now - data["last_accessed"])
        })
    return result

@app.delete("/api/sessions/{session_id}", dependencies=[Depends(verify_api_key)])
def delete_session(session_id: str):
    """Terminates and destroys a session early."""
    session = sessions.pop(session_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    try:
        terminate_container(session["container_name"], session["workspace_dir"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")
        
    return {"status": "deleted"}

@app.get("/mcp/{session_id}/sse", dependencies=[Depends(verify_api_key)])
async def proxy_sse(session_id: str):
    """Proxies FastMCP's SSE event stream in real-time chunk-by-chunk."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Update last accessed timestamp
    session["last_accessed"] = time.time()
    
    target_url = f"{session['target_url']}/sse"
    headers = {"Authorization": f"Bearer {session['internal_key']}"}
    
    async def event_generator():
        async with httpx.AsyncClient(timeout=None) as client:
            response = None
            max_retries = 8
            for attempt in range(max_retries):
                try:
                    req = client.build_request("GET", target_url, headers=headers)
                    response = await client.send(req, stream=True)
                    break
                except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                    if attempt == max_retries - 1:
                        logger.error("SSE stream proxy connection failed after %d attempts: %s", max_retries, str(e))
                        yield f"event: error\ndata: Target connection failed: {str(e)}\n\n".encode("utf-8")
                        return
                    logger.warning("Target SSE not ready yet, retrying in 0.5s (attempt %d/%d)...", attempt + 1, max_retries)
                    await asyncio.sleep(0.5)

            try:
                if response.status_code != 200:
                    yield f"event: error\ndata: Target SSE connection failed (status {response.status_code})\n\n".encode("utf-8")
                    return
                
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        # Rewrite the POST endpoint to route through this orchestrator gateway proxy
                        if line.startswith("data: /messages"):
                            line = line.replace("data: /messages", f"data: /mcp/{session_id}")
                        yield (line + "\n").encode("utf-8")
            except Exception as e:
                logger.error("SSE stream proxy error: %s", str(e))
                yield f"event: error\ndata: Proxy connection interrupted: {str(e)}\n\n".encode("utf-8")
            finally:
                await response.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/mcp/{session_id}", dependencies=[Depends(verify_api_key)])
@app.post("/mcp/{session_id}/", dependencies=[Depends(verify_api_key)])
async def proxy_jsonrpc(session_id: str, request: Request):
    """Proxies FastMCP's JSON-RPC tool call payload."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Update last accessed timestamp
    session["last_accessed"] = time.time()
    
    query_str = str(request.url.query)
    target_url = f"{session['target_url']}/messages/"
    if query_str:
        target_url += f"?{query_str}"
        
    headers = {
        "Authorization": f"Bearer {session['internal_key']}",
        "Content-Type": "application/json"
    }
    
    body = await request.body()
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            response = await client.post(target_url, content=body, headers=headers, timeout=60.0)
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except Exception as e:
            logger.exception("JSON-RPC proxy tool call error")
            raise HTTPException(status_code=502, detail=f"Bad Gateway proxying JSON-RPC: {str(e)}")
