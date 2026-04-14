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


@pytest.mark.asyncio
async def test_discovery_mcp_methods():
    # 1. Setup workspace
    root_dir = Path(__file__).parent.parent.parent
    tmp_dir = root_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    abs_tmp_dir = str(tmp_dir.resolve())

    # Ensure it's clean
    audit_file = tmp_dir / "mcp_audit.txt"
    if audit_file.exists():
        audit_file.unlink()

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
        client_session_timeout_seconds=60.0,  # Increased for larger downloads and hardening overhead
    )

    # 3. Define the Agent
    model_name = os.environ.get(
        "DEFAULT_MODEL", "openrouter/google/gemini-2.0-flash-001"
    )
    agent = Agent(
        name="DiscoveryAgent",
        instructions=(
            "You are a highly skilled discovery agent operating in a sandboxed Linux environment. "
            "You have access to common tools like curl, jq, grep, and sort. "
            "Expertly chain commands with pipes to achieve your goals efficiently."
        ),
        model=LitellmModel(model=model_name),
        mcp_servers=[server],
    )

    # 4. Run the Agent with Tracing and High Turn Limit
    mission = (
        "1. Download the definitive Model Context Protocol (MCP) JSON schema from: "
        "https://raw.githubusercontent.com/modelcontextprotocol/specification/main/schema/draft/schema.json\n"
        "2. Use a sophisticated bash pipeline (curl | jq | sort | uniq) to extract a clean list of all unique "
        "strings that appear to be JSON-RPC method names (e.g., 'initialize', 'tools/call', etc.).\n"
        "3. Save a report to `/workspace/mcp_audit.txt` containing the sorted list and a final count of methods found.\n"
        "4. If the provided URL fails, search for an alternative version (e.g., in the 'schema' folder) and try again."
    )

    # Enabling trace as requested
    with trace("MCP-Complex-Discovery"):
        async with server:
            result = await Runner.run(
                agent, mission, max_turns=20, run_config=RunConfig()
            )

            # 5. Verification
            print(f"\nDiscovery Agent Final Output:\n{result.final_output}")

            # Check if file exists on host
            assert audit_file.exists(), (
                "mcp_audit.txt was not created in the mounted tmp/ directory"
            )

            content = audit_file.read_text()
            print(f"\n--- mcp_audit.txt content ---\n{content}")

            # Basic sanity checks on content
            assert "initialize" in content.lower()
            # Most MCP versions have at least 10+ methods
            assert len(content.splitlines()) > 5


if __name__ == "__main__":
    asyncio.run(test_discovery_mcp_methods())
