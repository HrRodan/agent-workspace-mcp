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
    reason="OPENROUTER_API_KEY not found in environment",
)

# Reference F(400) value
# F(400) = 176023680645013966468226945392411250770384383304492191886725992896575345044216019675
# F(400) / 2 = 88011840322506983234113472696205625385192191652246095943362996448287672522108009837.5
EXPECTED_FIB_400_DIV_2 = (
    176023680645013966468226945392411250770384383304492191886725992896575345044216019675
    / 2
)


@pytest.mark.asyncio
async def test_agent_file_editing():
    # 1. Setup workspace
    root_dir = Path(__file__).parent.parent.parent
    tmp_dir = root_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    abs_tmp_dir = str(tmp_dir.resolve())

    # Ensure fib.py exists with initial content
    fib_file = tmp_dir / "fib.py"
    fib_content = (
        "def fibonacci(n):\n"
        "    if n <= 0: return 0\n"
        "    elif n == 1: return 1\n"
        "    a, b = 0, 1\n"
        "    for _ in range(2, n + 1):\n"
        "        a, b = b, a + b\n"
        "    return b\n\n"
        "if __name__ == '__main__':\n"
        "    n = 1123\n"
        "    result = fibonacci(n)\n"
        "    print(result)\n"
    )
    fib_file.write_text(fib_content)

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
        name="EditorAgent",
        instructions=(
            "You are a meticulous code editor. You locate files in your workspace, "
            "perform precise modifications using search_and_replace or apply_patch tools, "
            "and verify your changes by running the code."
        ),
        model=LitellmModel(model=model_name),
        mcp_servers=[server],
    )

    # 4. Run the Agent with Tracing
    mission = (
        "Modify the file `fib.py` in your workspace with the following changes:\n"
        "1. Change the input value `n = 1123` to `n = 400`.\n"
        "2. Modify the print statement to divide the result by 2 (e.g., `print(result / 2)`).\n"
        "After modifying, run the script and tell me the final numeric output."
    )

    with trace("MCP-Editing-Workflow"):
        async with server:
            result = await Runner.run(
                agent, mission, max_turns=15, run_config=RunConfig()
            )

            # 5. Verification
            print(f"\nEditor Agent Final Output: {result.final_output}")

            # Check updated file content on host
            updated_content = fib_file.read_text()
            print(f"\n--- Updated fib.py content ---\n{updated_content}")

            assert "n = 400" in updated_content
            assert "/ 2" in updated_content or "// 2" in updated_content

            # Check for numeric result in output
            # 8.801184032250698e+82 or similar
            output_str = str(result.final_output).lower()
            assert "8.8" in output_str
            assert (
                "82" in output_str
                or "10^82" in output_str
                or "10**82" in output_str
                or "e+82" in output_str
            )


if __name__ == "__main__":
    asyncio.run(test_agent_file_editing())
