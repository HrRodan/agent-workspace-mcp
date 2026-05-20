import os
import shutil
from unittest.mock import MagicMock, patch
from orchestrator.config import settings
from orchestrator.spawner import spawn_container, terminate_container

def test_spawn_container_production(mock_docker_client):
    """Verifies that spawning a container in production mode connects it to the bridge network."""
    mock_container = MagicMock()
    mock_container.id = "mock-id-prod-123"
    mock_docker_client.containers.run.return_value = mock_container

    # Enforce production mode
    with patch.object(settings, "orchestrator_mode", "production"):
        res = spawn_container("test-session-prod")
        
        assert res["container_id"] == "mock-id-prod-123"
        assert res["container_name"] == "mcp-agent-test-session-prod"
        assert res["target_url"] == "http://mcp-agent-test-session-prod:8000"
        assert os.path.exists(res["workspace_dir"])
        
        # Verify Docker parameters
        mock_docker_client.containers.run.assert_called_once()
        kwargs = mock_docker_client.containers.run.call_args[1]
        assert kwargs["network"] == settings.docker_network
        assert kwargs["ports"] is None
        assert kwargs["cap_drop"] == ["ALL"]
        assert kwargs["security_opt"] == ["no-new-privileges:true"]
        
        # Cleanup
        shutil.rmtree(res["workspace_dir"], ignore_errors=True)

def test_spawn_container_development(mock_docker_client):
    """Verifies that spawning a container in development mode maps random host ports."""
    mock_container = MagicMock()
    mock_container.id = "mock-id-dev-123"
    mock_container.ports = {"8000/tcp": [{"HostPort": "32845"}]}
    mock_docker_client.containers.run.return_value = mock_container

    # Enforce development mode
    with patch.object(settings, "orchestrator_mode", "development"):
        res = spawn_container("test-session-dev")
        
        assert res["container_id"] == "mock-id-dev-123"
        assert res["target_url"] == "http://127.0.0.1:32845"
        assert os.path.exists(res["workspace_dir"])
        
        # Verify Docker parameters
        mock_docker_client.containers.run.assert_called_once()
        kwargs = mock_docker_client.containers.run.call_args[1]
        assert kwargs["network"] == "bridge"
        assert "8000/tcp" in kwargs["ports"]
        
        # Cleanup
        shutil.rmtree(res["workspace_dir"], ignore_errors=True)

def test_terminate_container(mock_docker_client):
    """Verifies that terminating a container stops, removes, and cleans workspace directory."""
    mock_container = MagicMock()
    mock_docker_client.containers.get.return_value = mock_container
    
    # Create dummy workspace dir
    temp_dir = "/tmp/test-terminate-dir"
    os.makedirs(temp_dir, exist_ok=True)
    
    terminate_container("mcp-agent-test", temp_dir)
    
    # Verify container stoppage and removal
    mock_docker_client.containers.get.assert_called_once_with("mcp-agent-test")
    mock_container.stop.assert_called_once_with(timeout=5)
    mock_container.remove.assert_called_once_with(force=True)
    
    # Verify workspace deletion
    assert not os.path.exists(temp_dir)
