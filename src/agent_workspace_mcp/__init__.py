"""Agent Workspace MCP: A sandboxed agentic workspace for LLMs."""

import os
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = os.getenv("MCP_SERVER_VERSION") or version("agent-workspace-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

