import os
import asyncio
import pytest
from pathlib import Path
from dotenv import load_dotenv
from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from agents.extensions.models.litellm_model import LitellmModel

# Load environment variables (API keys, etc.)
load_dotenv()

# Skip tests if no API key is available
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not found in environment",
)

@pytest.mark.asyncio
async def test_readme_boilerplate(agent_workspace: Path):
    """
    Validates the 'Quick Start' programmatic example from README.md.
    Uses the local image and OpenAI Agents SDK.
    """
    # 1. Setup workspace
    abs_tmp_dir = str(agent_workspace)

    # Environment-specific values for the current system
    uid = os.getuid()
    gid = os.getgid()
    
    model_name = os.environ.get("DEFAULT_MODEL", "openrouter/google/gemini-2.0-flash-001")

    # 1. Configure the MCP Server to run via Docker (matching README flags)
    server = MCPServerStdio(
        name="Sandboxed Workspace",
        params={
            "command": "docker",
            "args": [
                "run", "-i", "--rm", "--init",
                "--memory=2g", "--cpus=2.0",
                "--pids-limit=256",
                "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
                "--read-only",
                "--tmpfs", "/tmp:size=64m",
                "--tmpfs", "/home/mcpuser/.cache:size=512m",
                "--env", "UV_PROJECT_ENVIRONMENT=/workspace/.venv_container",
                "--user", f"{uid}:{gid}",
                "-v", f"{abs_tmp_dir}:/workspace",
                "agent-workspace-mcp",
            ],
        },
        client_session_timeout_seconds=60.0,
    )

    # 2. Attach server to the Agent
    agent = Agent(
        name="WorkspaceAgent",
        instructions="You are a coding agent with access to a secure workspace. Use your tools to manage files and run bash commands.",
        model=LitellmModel(model=model_name),
        mcp_servers=[server],
    )

    # 3. Execute a workflow
    async with server:
        result = await Runner.run(
            agent, 
            "Create a python script `readme_fib.py` in the workspace to print the first 10 Fibonacci numbers, then run it."
        )
        output_str = str(result.final_output)
        
        # Verification
        print(f"\nAgent's Final Output:\n{output_str}")
        
        # Check if the file was actually created on the host
        fib_file = agent_workspace / "readme_fib.py"
        assert fib_file.exists(), "readme_fib.py was not created in the workspace"
        
        # Verify output contains numbers (Fibonacci sequence: 0, 1, 1, 2, 3, 5, 8, 13, 21, 34)
        for num in ["0", "1", "2", "3", "5", "8", "13", "21", "34"]:
            assert num in output_str, f"Expected Fibonacci number {num} not found in agent output"

if __name__ == "__main__":
    asyncio.run(test_readme_boilerplate())
