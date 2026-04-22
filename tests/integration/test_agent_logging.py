import os
import pytest
from pathlib import Path
from dotenv import load_dotenv

from agents import Agent, Runner, RunConfig
from agents.mcp import MCPServerStdio
from agents.extensions.models.litellm_model import LitellmModel

# Load environment variables
load_dotenv()

# Skip tests if no API key is available
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not found in environment",
)

@pytest.mark.asyncio
async def test_agent_audit_logging(agent_workspace: Path):
    """Verify that a real agent run generates persistent tool audit logs in the workspace."""
    
    # 1. Setup workspace with a dummy file
    (agent_workspace / "mission.txt").write_text("The secret code is: LOGGING-WORKS")
    
    # 2. Configure the MCP Server (Dockerized)
    # We use the local 'agent-workspace-mcp' image we just built
    server = MCPServerStdio(
        name="Sandboxed Workspace",
        params={
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "--user", f"{os.getuid()}:{os.getgid()}", # Match host permissions
                "-v", f"{agent_workspace}:/workspace",
                "agent-workspace-mcp",
            ],
        },
        client_session_timeout_seconds=60.0,
    )

    # 3. Define the Agent
    model_name = os.environ.get("DEFAULT_MODEL", "openrouter/google/gemini-2.0-flash-001")
    agent = Agent(
        name="AuditAgent",
        instructions=(
            "You are a test agent. Your goal is to trigger tool calls so we can check the logs. "
            "1. List the files in the workspace. "
            "2. Read the content of 'mission.txt'."
        ),
        model=LitellmModel(model=model_name),
        mcp_servers=[server],
    )

    # 4. Run the Agent
    async with server:
        await Runner.run(
            agent, 
            "Execute your instructions and report the secret code.", 
            max_turns=5, 
            run_config=RunConfig()
        )

    # 5. Verification: Check that the log file exists and contains tool calls
    log_file = agent_workspace / ".mcp" / "server.log"
    
    assert log_file.exists(), "Audit log file was not created in .mcp/"
    
    log_content = log_file.read_text()
    print(f"\n--- Captured Server Audit Log ---\n{log_content}")
    
    # Assert standard startup messages
    assert "Agent Workspace MCP server starting..." in log_content
    assert "Workspace root: /workspace" in log_content
    
    # Assert tool calls are logged with our new structured format
    assert "TOOL_CALL list_directory" in log_content
    assert "TOOL_DONE list_directory [OK]" in log_content
    assert "TOOL_CALL read_file" in log_content
    assert "filepath='mission.txt'" in log_content
    assert "TOOL_DONE read_file [OK]" in log_content
    assert "1 lines returned" in log_content or "LOGGING-WORKS" in log_content # summary or content snippet
