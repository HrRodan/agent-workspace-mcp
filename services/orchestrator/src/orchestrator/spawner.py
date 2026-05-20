import os
import secrets
import shutil
import tempfile
import logging
import docker
from orchestrator.config import settings

logger = logging.getLogger("orchestrator.spawner")

class SpawnerError(Exception):
    pass

def get_docker_client():
    try:
        return docker.from_env()
    except Exception as e:
        logger.error("Failed to initialize Docker client: %s", str(e))
        raise SpawnerError(f"Docker client initialization failed: {str(e)}")

def spawn_container(session_id: str) -> dict:
    """
    Spawns an isolated agent container on the host Docker daemon.
    Enforces security boundaries, resource limits, and maps ephemeral directories.
    """
    client = get_docker_client()
    
    # 1. Create a secure, isolated workspace directory on the host
    try:
        os.makedirs(settings.base_workspace_dir, exist_ok=True)
        workspace_dir = tempfile.mkdtemp(
            dir=settings.base_workspace_dir, 
            prefix=f"session-{session_id}-"
        )
        # Ensure that the unprivileged container user (1000:1000) can read/write the volume
        os.chmod(workspace_dir, 0o777)
    except Exception as e:
        logger.error("Failed to create session workspace dir: %s", str(e))
        raise SpawnerError(f"Workspace directory creation failed: {str(e)}")

    # 2. Generate a secure, unique API key for this specific container session
    internal_key = secrets.token_urlsafe(32)
    container_name = f"mcp-agent-{session_id}"
    
    # 3. Configure Docker container spawn arguments
    run_kwargs = {
        "image": settings.agent_image,
        "name": container_name,
        "detach": True,
        "init": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "mem_limit": "2g",
        "cpu_quota": 200000,
        "pids_limit": 256,
        "user": "1000:1000",
        "tmpfs": {"/tmp": "size=64m", "/home/mcpuser/.cache": "size=512m"},
        "volumes": {workspace_dir: {"bind": "/workspace", "mode": "rw"}},
        "environment": {
            "MCP_TRANSPORT": "http",
            "MCP_API_KEY": internal_key,
            "MCP_HOST": "0.0.0.0",
            "MCP_PORT": "8000"
        }
    }
    
    # 4. Apply network-specific configurations based on the environment mode
    is_prod = settings.orchestrator_mode.lower() == "production"
    if is_prod:
        # Production Mode: Communicate entirely within the virtual bridge network
        run_kwargs["network"] = settings.docker_network
        run_kwargs["ports"] = None  # No host ports exposed
        target_url = f"http://{container_name}:8000"
    else:
        # Development Mode: Bind to a random port on localhost
        run_kwargs["ports"] = {"8000/tcp": ("127.0.0.1", None)}
        # Set network explicitly to standard bridge to avoid mcp-network missing during local dev
        run_kwargs["network"] = "bridge"

    # 5. Spin up the container
    try:
        logger.info("Spawning container %s (mode=%s)...", container_name, settings.orchestrator_mode)
        container = client.containers.run(**run_kwargs)
    except Exception as e:
        logger.error("Failed to run Docker container: %s", str(e))
        # Cleanup directory
        shutil.rmtree(workspace_dir, ignore_errors=True)
        raise SpawnerError(f"Docker container run failed: {str(e)}")
        
    # 6. Extract connection information for development mode
    if not is_prod:
        try:
            container.reload()
            ports_config = container.ports.get("8000/tcp")
            if not ports_config:
                raise SpawnerError("Container did not bind port 8000/tcp")
            host_port = ports_config[0]["HostPort"]
            target_url = f"http://127.0.0.1:{host_port}"
        except Exception as e:
            logger.error("Failed to retrieve host port: %s", str(e))
            # Cleanup container and directory
            try:
                container.stop(timeout=5)
                container.remove(force=True)
            except Exception:
                pass
            shutil.rmtree(workspace_dir, ignore_errors=True)
            raise SpawnerError(f"Host port allocation retrieval failed: {str(e)}")

    logger.info("Container %s successfully spawned. Target URL: %s", container_name, target_url)
    return {
        "container_id": container.id,
        "container_name": container_name,
        "internal_key": internal_key,
        "workspace_dir": workspace_dir,
        "target_url": target_url
    }

def terminate_container(container_name: str, workspace_dir: str) -> None:
    """
    Terminates the sibling container and recursively purges the workspace directory.
    """
    client = get_docker_client()
    
    # 1. Stop and remove Docker container
    try:
        logger.info("Stopping container %s...", container_name)
        container = client.containers.get(container_name)
        container.stop(timeout=5)
        container.remove(force=True)
        logger.info("Container %s cleanly destroyed.", container_name)
    except docker.errors.NotFound:
        logger.warning("Container %s not found during termination.", container_name)
    except Exception as e:
        logger.error("Error destroying container %s: %s", container_name, str(e))

    # 2. Recursively delete temp workspace directory
    if os.path.exists(workspace_dir):
        try:
            shutil.rmtree(workspace_dir, ignore_errors=True)
            logger.info("Workspace directory %s cleanly purged.", workspace_dir)
        except Exception as e:
            logger.error("Error deleting workspace %s: %s", workspace_dir, str(e))
