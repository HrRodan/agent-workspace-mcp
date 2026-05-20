from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from orchestrator.main import app
from orchestrator.config import settings
from orchestrator.reaper import sessions

client = TestClient(app)

def test_health_endpoint():
    """Verifies that the health check responds without authentication."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_auth_rejection():
    """Verifies that endpoints reject unauthorized requests."""
    response = client.post("/api/sessions")
    assert response.status_code == 401  # Missing bearer token
    
    headers = {"Authorization": "Bearer invalid-key"}
    response = client.post("/api/sessions", headers=headers)
    assert response.status_code == 401  # Invalid key

@patch("orchestrator.main.spawn_container")
def test_session_lifecycle(mock_spawn, mock_docker_client):
    """Tests the session creation, listing, and deletion flow under auth."""
    mock_spawn.return_value = {
        "container_name": "mcp-agent-test-123",
        "workspace_dir": "/tmp/session-test-123",
        "target_url": "http://127.0.0.1:45000",
        "internal_key": "internal-secret"
    }
    
    headers = {"Authorization": f"Bearer {settings.orchestrator_api_key}"}
    
    # 1. Create session
    response = client.post("/api/sessions", headers=headers)
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    assert session_id is not None
    
    # Verify registered in sessions dictionary
    assert session_id in sessions
    assert sessions[session_id]["container_name"] == "mcp-agent-test-123"
    
    # 2. List sessions
    response = client.get("/api/sessions", headers=headers)
    assert response.status_code == 200
    sessions_list = response.json()
    assert len(sessions_list) == 1
    assert sessions_list[0]["session_id"] == session_id
    assert sessions_list[0]["target_url"] == "http://127.0.0.1:45000"
    
    # 3. Delete session
    with patch("orchestrator.main.terminate_container") as mock_term:
        response = client.delete(f"/api/sessions/{session_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        
        # Verify removed from registry
        assert session_id not in sessions
        mock_term.assert_called_once_with("mcp-agent-test-123", "/tmp/session-test-123")

@patch("httpx.AsyncClient.post")
def test_proxy_jsonrpc(mock_post):
    """Verifies proxying of JSON-RPC POST payloads to the agent container."""
    session_id = "test-proxy-sid"
    sessions[session_id] = {
        "container_name": "mcp-agent-test-rpc",
        "workspace_dir": "/tmp/session-rpc",
        "target_url": "http://127.0.0.1:46000",
        "internal_key": "internal-secret-key",
        "last_accessed": 100.0
    }
    
    headers = {"Authorization": f"Bearer {settings.orchestrator_api_key}"}
    
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.content = b'{"jsonrpc": "2.0", "result": "success", "id": 1}'
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_post.return_value = mock_response
    
    payload = {"jsonrpc": "2.0", "method": "list_tools", "id": 1}
    response = client.post(f"/mcp/{session_id}/", headers=headers, json=payload)
    
    assert response.status_code == 200
    assert response.json()["result"] == "success"
    
    # Verify target POST call details
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://127.0.0.1:46000/messages/"
    assert kwargs["headers"]["Authorization"] == "Bearer internal-secret-key"
    
    # Verify idle last accessed timestamp updated
    assert sessions[session_id]["last_accessed"] > 100.0
    
    # Clean up
    sessions.pop(session_id, None)
