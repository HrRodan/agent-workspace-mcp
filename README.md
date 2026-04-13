# Sandboxed Agent Workspace MCP Server

[![CI](https://github.com/HrRodan/agent-workspace-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/HrRodan/agent-workspace-mcp/actions/workflows/ci.yml)

A unified Model Context Protocol (MCP) server providing a highly secure, containerized workspace for Large Language Models (LLMs). It enables autonomous coding, testing, and debugging in an isolated "agentic playground" without risking the host machine.

## 🚀 Features

- **Isolated Execution**: Runs entirely inside a Docker container with restricted capabilities (`--cap-drop=ALL`).
- **Filesystem Tools**: Securely read, write, list, and search files within the `/workspace` directory.
- **Bash Execution**: Run shell commands with configurable timeouts.
- **Python Power**: Deep integration with `uv` for lightning-fast dependency management and project scaffolding.
- **Safe Editing**: `search_and_replace` with AST validation for Python, JSON, and TOML.
- **Unified Diffs**: Apply standard `.patch` files using the native `patch` utility.
- **Observability**: Real-time logging to the MCP client and persistent audit logs.

## 🛠 Architecture

```mermaid
graph TD
    Client[MCP Client (Claude/Cursor)] -- stdio (JSON-RPC) --> Server[FastMCP Server]
    subgraph Docker Sandbox
        Server -- Subprocess --> Bash[Bash/Shell]
        Server -- API --> FS[Filesystem Utilities]
        Server -- Subprocess --> UV[UV / Ruff]
    end
    FS -- Mount --> HostVolume[/workspace]
```

## 📦 Quick Start

### 1. Build the Image
```bash
docker build -t agent-workspace-mcp .
```

### 2. Configure Claude Desktop
Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agent-workspace-mcp": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--memory=2g", "--cpus=2.0",
        "--pids-limit=256",
        "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
        "--read-only",
        "--tmpfs", "/tmp:size=64m",
        "--tmpfs", "/home/mcpuser/.cache:size=512m",
        "--env", "UV_PROJECT_ENVIRONMENT=/workspace/.venv_container",
        "--user", "1000:1000",
        "-v", "/path/to/your/projects:/workspace",
        "agent-workspace-mcp"
      ]
    }
  }
}
```
*Note: Replace `/path/to/your/projects` with a local directory and `1000:1000` with your local UID:GID if on Linux.*

## 🛠 Tool Reference

- **`read_file`**: Read text files (max 1MB).
- **`write_file`**: Write/overwrite files (auto-creates directories).
- **`list_directory`**: Explore the workspace structure.
- **`get_file_info`**: Detailed metadata (size, time, perms).
- **`search_workspace`**: Find files using glob patterns.
- **`run_bash`**: Execute shell commands with a 30s timeout by default.
- **`lint_workspace`**: Run `ruff` check and format on your code.
- **`apply_patch`**: Apply Unified Diffs securely.
- **`search_and_replace`**: Atomic string replacement with syntax validation.

## 🤖 Agent Workflow Guidelines

### Workflow A: Single Scripts
Instruct your agent to use PEP 723 inline metadata for simple scripts:
```python
# /// script
# dependencies = ["requests", "pandas"]
# ///
import requests
...
```
Execute via `run_bash(command="uv run script.py")`.

### Workflow B: Complex Projects
For multi-file projects:
1. `run_bash(command="uv init")`
2. `run_bash(command="uv add <dependency>")`
3. Manage files and execute via `uv run`.

## ⚙️ Configuration

| Variable | Default | Description |
|---|---|---|
| `WORKSPACE_ROOT` | `/workspace` | Root directory for all operations. |
| `COMMAND_TIMEOUT` | `30` | Seconds before killing a subprocess. |
| `MAX_SEARCH_RESULTS` | `50` | Limit for glob results. |
| `MAX_READ_SIZE_BYTES` | `1048576` | Limit for inline file reads (1MB). |
| `LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, etc.). |

## 🛡 Security Model

- **No Privilege**: Container runs as a non-root `mcpuser`.
- **Read-Only Root**: The container's system files cannot be modified.
- **Resource Caps**: RAM and CPU are strictly limited.
- **Path Guard**: `safe_path` prevents traversal attacks outside the mounted `/workspace`.
- **Ephemeral**: Containers are destroyed immediately upon client disconnection.

## 🤝 Contributing

1. Install dependencies: `uv sync`
2. Run unit tests: `uv run pytest tests/ --ignore=tests/test_live_workflow.py`
3. Run E2E tests (requires `OPENROUTER_API_KEY`): `uv run pytest tests/test_live_workflow.py`

---
&copy; 2026 HrRodan. Licensed under MIT.
