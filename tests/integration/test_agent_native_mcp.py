import os
import asyncio
import pytest
from pathlib import Path
from dotenv import load_dotenv
from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from agents.extensions.models.litellm_model import LitellmModel

# Load environment variables
load_dotenv()

# Skip tests if no API key is available
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not found in environment",
)

# Reference F(1123) value
EXPECTED_FIB_1123 = 2206149801926881369449793988369307276503750393504822131703106783938347774605706059071641074804018140369700374109454281139064746057391600969033573289591371894612233398633860766372562131519333715985437361719040191464605466213379195461557


@pytest.mark.asyncio
async def test_native_mcp_fibonacci():
    # 1. Setup workspace
    root_dir = Path(__file__).parent.parent.parent
    tmp_dir = root_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    abs_tmp_dir = str(tmp_dir.resolve())

    # Ensure it's clean for the test
    fib_file = tmp_dir / "fib.py"
    if fib_file.exists():
        fib_file.unlink()

    # 2. Configure Native MCP Server
    # We use the docker image we built previously
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
        client_session_timeout_seconds=60.0,  # Increased for larger downloads and hardening overhead
    )

    # 3. Define the Agent
    model_name = os.environ.get(
        "DEFAULT_MODEL", "openrouter/google/gemini-2.0-flash-001"
    )
    agent = Agent(
        name="FibonacciSolver",
        instructions=(
            "You are a specialized coding agent. Your goal is to solve mathematical "
            "problems by writing and executing Python scripts in your workspace. "
            "Use your tools to manage files and run bash commands."
        ),
        model=LitellmModel(model=model_name),
        mcp_servers=[server],
    )

    # 4. Run the Agent
    prompt = (
        "Calculate the 1123rd Fibonacci number. "
        "Steps: 1. Write a script `fib.py` to calculate it. "
        "2. Run the script and show me the output result."
    )

    async with server:
        result = await Runner.run(agent, prompt)
        output_str = str(result.final_output)

        # 5. Verification
        print(f"\nAgent's Final Output: {output_str}")

        assert fib_file.exists(), "fib.py was not created in the mounted tmp/ directory"

        # Robust comparison: extract all large numbers from output
        import re

        found_numbers = re.findall(r"\d+", output_str)
        assert any(n == str(EXPECTED_FIB_1123) for n in found_numbers), (
            f"Agent output did not contain the correct F(1123) value. Found: {found_numbers}"
        )


if __name__ == "__main__":
    asyncio.run(test_native_mcp_fibonacci())
