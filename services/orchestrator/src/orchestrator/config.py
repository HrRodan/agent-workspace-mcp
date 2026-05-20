from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # API key required to authenticate with the Orchestrator Gateway
    orchestrator_api_key: str = "super-secret-gateway-key"
    
    # "production" (container-to-container on bridge network) or "development" (host loopback mapping)
    orchestrator_mode: str = "production"
    
    # Docker bridge network name to connect containers
    docker_network: str = "mcp-network"
    
    # Image name for the spawned agent container
    agent_image: str = "agent-workspace-mcp:latest"
    
    # Inactivity duration before the reaper prunes the session
    session_timeout_seconds: int = 1800
    
    # Base folder on the host to spawn ephemeral workspaces
    base_workspace_dir: str = "/tmp/mcp-workspaces"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

# Instantiate global settings
settings = Settings()
