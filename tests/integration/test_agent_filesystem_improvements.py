import os
import pytest
from pathlib import Path
from dotenv import load_dotenv

from agents import Agent, Runner, trace, RunConfig
from agents.mcp import MCPServerStdio
from .model_helper import get_openrouter_model

# Load environment variables
load_dotenv()

# Skip tests if no API key is available
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not found in environment",
)

@pytest.mark.asyncio
async def test_agent_filesystem_improvements(agent_workspace: Path):
    """
    Live Agent Test: Verifying new filesystem and editing improvements.
    1. Agent list_directory to explore.
    2. Agent read_file with limit to check content.
    3. Agent search_and_replace with multi-edit.
    """
    # 1. Setup workspace with a multi-level structure and a "large" file
    (agent_workspace / "src").mkdir()
    (agent_workspace / "scripts").mkdir()
    
    app_py = agent_workspace / "src" / "app.py"
    app_py.write_text("\n".join([f"line_{i:03d} = 'some data'" for i in range(200)]))
    
    config_yaml = agent_workspace / "config.yaml"
    config_yaml.write_text("environment: production\nversion: 1.0.0\n")

    # 2. Configure Native MCP Server
    abs_tmp_dir = str(agent_workspace)
    server = MCPServerStdio(
        name="Filesystem-Improvement-Verify",
        params={
            "command": "docker",
            "args": [
                "run", "-i", "--rm", "--init",
                "--user", "1000:1000",
                "--security-opt", "no-new-privileges",
                "--cap-drop", "ALL",
                "-v", f"{abs_tmp_dir}:/workspace",
                "agent-workspace-mcp",
            ],
        },
        client_session_timeout_seconds=60.0,
    )

    # 3. Define the Agent
    model_name = os.environ.get("DEFAULT_MODEL", "openrouter/google/gemini-2.0-flash-001")
    agent = Agent(
        name="ExplorerAgent",
        instructions=(
            "You are an efficient developer. Use list_directory to see what's in the workspace. "
            "When reading files, remember that read_file defaults to 100 lines. Use offset/limit "
            "if you need to see more. Use search_and_replace for multi-edit operations."
        ),
        model=get_openrouter_model(model_name),
        mcp_servers=[server],
    )

    # 4. Mission
    mission = (
        "1. Explore the workspace and tell me what's in 'src/'.\n"
        "2. Read the end of 'src/app.py' (beyond line 150) to see what the last line is.\n"
        "3. Apply two changes to 'config.yaml' in one tool call: change 'production' to 'staging' "
        "and '1.0.0' to '1.1.0'.\n"
        "4. Confirm all steps were successful."
    )

    with trace("MCP-Improvements-Workflow"):
        async with server:
            result = await Runner.run(
                agent, mission, max_turns=10, run_config=RunConfig()
            )

            # 5. Verification
            output_str = str(result.final_output)
            print(f"\nExplorer Agent Output: {output_str}")

            # Verify yaml changes
            yaml_content = config_yaml.read_text()
            assert "environment: staging" in yaml_content
            assert "version: 1.1.0" in yaml_content
            
            # Verify agent saw the end of the file
            assert "199" in output_str or "last line" in output_str.lower()
