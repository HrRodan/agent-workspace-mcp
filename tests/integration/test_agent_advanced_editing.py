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
async def test_advanced_editing_dry_run(agent_workspace: Path):
    """
    Test that the agent can use search_and_replace with dry_run first,
    verify the unified diff, and then apply it atomically for multiple edits.
    """
    # 1. Setup workspace
    abs_tmp_dir = str(agent_workspace)

    target_file = agent_workspace / "calculator.py"
    target_file.write_text(
        "def add(a, b):\n"
        "    return a + b\n\n"
        "def subtract(a, b):\n"
        "    return a - b\n"
    )

    # 2. Configure Native MCP Server
    server = MCPServerStdio(
        name="Sandboxed Workspace",
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
        name="AdvancedEditor",
        instructions=(
            "You are an expert editor in a sandboxed linux environment. "
            "When making file edits, ALWAYS use 'dry_run: true' first to "
            "preview the changes via the unified diff. Once you verify the diff, "
            "apply the changes by setting 'dry_run: false'."
        ),
        model=get_openrouter_model(model_name),
        mcp_servers=[server],
    )

    # 4. Mission
    mission = (
        "1. Preview an edit to 'calculator.py' using dry_run=True. Change `return a + b` to `return a + b + 0` "
        "and `return a - b` to `return a - b - 0` in a single multi-edit tool call.\n"
        "2. Once you see the dry_run unified diff output, make the exact same tool call but with dry_run=False to apply it.\n"
        "3. Confirm the final file state."
    )

    with trace("MCP-Advanced-Editing-DryRun"):
        async with server:
            result = await Runner.run(agent, mission, max_turns=12, run_config=RunConfig())

            # 5. Verification
            output_str = str(result.final_output)
            print(f"\nAdvanced Editor Agent Output: {output_str}")

            # Check that the file was actually changed
            content = target_file.read_text()
            assert "return a + b + 0" in content
            assert "return a - b - 0" in content
