"""Agent Workspace MCP: A sandboxed agentic workspace for LLMs."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("agent-workspace-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

