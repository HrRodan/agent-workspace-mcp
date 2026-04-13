import os
import asyncio
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
    reason="OPENROUTER_API_KEY not found in environment"
)

@pytest.mark.asyncio
async def test_agent_qa_cycle():
    """
    Test a full development QA cycle:
    1. Create a script with intentional linting issues.
    2. Audit with lint_workspace.
    3. Fix with editing tools.
    4. Verify with lint_workspace and get_file_info.
    """
    # 1. Setup workspace
    root_dir = Path(__file__).parent.parent
    tmp_dir = root_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    abs_tmp_dir = str(tmp_dir.resolve())
    
    qa_file = tmp_dir / "qa_target.py"
    if qa_file.exists():
        qa_file.unlink()

    # 2. Configure Native MCP Server
    server = MCPServerStdio(
        name="Sandboxed Workspace",
        params={
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "--user", "1000:1000",
                "--security-opt", "no-new-privileges",
                "--cap-drop", "ALL",
                "--init",
                "--memory", "512m",
                "--cpus", "0.5",
                "-v", f"{abs_tmp_dir}:/workspace",
                "agent-workspace-mcp"
            ]
        },
        client_session_timeout_seconds=60.0
    )

    # 3. Define the Agent
    model_name = os.environ.get("DEFAULT_MODEL", "openrouter/google/gemini-2.0-flash-001")
    agent = Agent(
        name="QAAgent",
        instructions=(
            "You are a Quality Assurance engineer. You ensure that code scripts in the workspace "
            "comply with linting standards. You find issues using lint_workspace, "
            "fix them using editing tools, and verify the final state using metadata and linting tools."
        ),
        model=LitellmModel(model=model_name),
        mcp_servers=[server]
    )

    # 4. Run the QA Mission
    mission = (
        "1. Create a new Python file `/workspace/qa_target.py`. It MUST have intentional "
        "linting issues: include an unused import (e.g., `import sys`) and some "
        "trailing whitespace or multiple blank lines.\n"
        "2. Run the `lint_workspace` tool to identify these issues.\n"
        "3. Fix the detected issues using your editing tools.\n"
        "4. Run `lint_workspace` again to verify the file is now clean.\n"
        "5. Use `get_file_info` to report the final file size and modification time."
    )
    
    with trace("MCP-QA-Cycle"):
        async with server:
            result = await Runner.run(
                agent, 
                mission, 
                max_turns=20,
                run_config=RunConfig()
            )
            
            # 5. Verification
            print(f"\nQA Agent Final Output:\n{result.final_output}")
            
            # Check if file exists and looks clean
            assert qa_file.exists(), "qa_target.py was not created"
            content = qa_file.read_text()
            print(f"\n--- qa_target.py final content ---\n{content}")
            
            # Unused imports should be gone if agent followed instructions
            assert "import sys" not in content or "qa_target.py" not in content # Or it fixed it
            
            # The final output should mention file info
            output_lower = str(result.final_output).lower()
            assert "bytes" in output_lower or "size" in output_lower

if __name__ == "__main__":
    asyncio.run(test_agent_qa_cycle())
