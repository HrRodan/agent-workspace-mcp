import os
import pytest
from pathlib import Path
from dotenv import load_dotenv

from agents import Agent, Runner, trace, RunConfig
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
async def test_agent_tool_error_recovery(agent_workspace: Path):
    """
    Test that the agent can recover from a ToolError.
    We tell the agent to read 'secret.txt', but only 'hidden_secret.txt' exists.
    The agent should receive an error, list the directory, find the right file, and succeed.
    """
    # 1. Setup workspace
    abs_tmp_dir = str(agent_workspace)
    secret_file = agent_workspace / "hidden_secret.txt"
    secret_file.write_text("The password is 'antigravity'")

    # 2. Configure Native MCP Server
    server = MCPServerStdio(
        name="Sandboxed Workspace",
        params={
            "command": "docker",
            "args": [
                "run",
                "-i",
                "--rm",
                "--user",
                "1000:1000",
                "--security-opt",
                "no-new-privileges",
                "--cap-drop",
                "ALL",
                "--init",
                "--memory",
                "512m",
                "--cpus",
                "0.5",
                "-v",
                f"{abs_tmp_dir}:/workspace",
                "agent-workspace-mcp",
            ],
        },
        client_session_timeout_seconds=60.0,
    )

    # 3. Define the Agent
    model_name = os.environ.get(
        "DEFAULT_MODEL", "openrouter/google/gemini-2.0-flash-001"
    )
    agent = Agent(
        name="RecoveryAgent",
        instructions=(
            "You are a helpful assistant. If a tool returns an error, "
            "analyze the error message and try to fix the problem by using other tools "
            "to discover the correct state of the workspace."
        ),
        model=LitellmModel(model=model_name),
        mcp_servers=[server],
    )

    # 4. Run the Agent
    mission = (
        "Tell me the password stored in 'secret.txt'. "
    )

    with trace("MCP-Error-Recovery-Workflow"):
        async with server:
            result = await Runner.run(
                agent, mission, max_turns=10, run_config=RunConfig()
            )

            print(f"\nRecovery Agent Final Output: {result.final_output}")
            
            # The agent should have found the password
            assert "antigravity" in str(result.final_output).lower()

if __name__ == "__main__":
    # To run this manually:
    # 1. Ensure docker image is built: docker build -t agent-workspace-mcp .
    # 2. Set OPENROUTER_API_KEY
    # 3. python tests/integration/test_agent_error_recovery.py
    from pathlib import Path
    
    # Simple mock for agent_workspace fixture if run as script
    class MockPath:
        def __init__(self, p): self.p = Path(p)
        def __div__(self, other): return MockPath(self.p / other)
        def __truediv__(self, other): return MockPath(self.p / other)
        def write_text(self, t): self.p.write_text(t)
        def __str__(self): return str(self.p)
    
    # This won't work perfectly as a script without the pytest fixtures, 
    # but it gives the idea.
    print("Run via: uv run pytest tests/integration/test_agent_error_recovery.py")
