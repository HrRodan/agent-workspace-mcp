# 🛡️ Agent Workspace MCP Server

[![CI](https://github.com/HrRodan/agent-workspace-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/HrRodan/agent-workspace-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/release/python-3140/)

A unified Model Context Protocol (MCP) server providing a **highly secure, containerized workspace** for Large Language Models (LLMs). It acts as an isolated "agentic playground" where agents can autonomously code, test, and debug without risking the host machine.

---

## ✨ Features

- **🏗️ Full Project Lifecycle**: Bootstrap projects with `uv init`, manage dependencies with `uv add`, and execute via `uv run`.
- **🐚 Secure Bash Access**: Execute shell commands with mandatory timeouts and merged output streams.
- **📂 Robust Filesystem**: Path-traversal protected operations for reading, writing, and searching the workspace.
- **🛡️ Multi-Layer Security**: Non-root execution, dropped capabilities, resource limits, and a read-only root filesystem.
- **⚡ Fast Editing**: Atomic `search_and_replace` with syntax validation for Python, JSON, and TOML.
- **🩹 Unified Diffs**: Apply standard `.patch` files securely using the native `patch` utility.
- **📊 Real-time Observability**: Direct logging to MCP client UI and persistent rotating audit logs.

---

## 🏗️ Architecture

```mermaid
graph TD
    Client[MCP Client (Claude/Cursor)] -- "stdio (JSON-RPC)" --> Server[FastMCP Server]
    subgraph "Docker Sandbox (Isolated)"
        Server -- "Subprocess" --> Bash[Bash / Shell]
        Server -- "API" --> FS[Filesystem Utilities]
        Server -- "Subprocess" --> UV[UV / Ruff / Python]
    end
    FS -- "Mount" --> HostVolume["/workspace (Host Directory)"]
```

---

## 📦 Quick Start

### 1. Build the Docker Image
```bash
docker build -t agent-workspace-mcp .
```

### 2. Configure Your MCP Client
Add the following configuration to your `claude_desktop_config.json` or Cursor settings.

```json
{
  "mcpServers": {
    "agent-workspace-mcp": {
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
        "--user", "1000:1000",
        "-v", "/path/to/your/projects:/workspace",
        "agent-workspace-mcp"
      ]
    }
  }
}
```

> [!IMPORTANT]
> **Linux Users:** Replace `1000:1000` with your actual UID:GID (run `id -u` and `id -g`). Claude Desktop does not expand environment variables.
> **Signal Handling:** The `--init` flag is essential for proper signal forwarding and zombie process reaping.

---

## 🛠️ Tool Reference

| Tool | Description |
|---|---|
| `read_file` | Reads text files from the workspace (max 1MB). |
| `write_file` | Writes or overwrites files (automatically creates parent directories). |
| `list_directory` | Lists directory contents with size and type info. |
| `get_file_info` | Returns detailed metadata (ISO timestamps, octal permissions). |
| `search_workspace` | Searches for files using glob patterns (e.g., `**/*.py`). |
| `run_bash` | Executes shell commands in `/workspace` with a 30s timeout. |
| `lint_workspace` | Proactively runs `ruff check` and `ruff format` on code. |
| `apply_patch` | Securely applies standard Unified Diffs (`.patch` files). |
| `search_and_replace` | Atomic string replacement with AST validation for Python, JSON, and TOML. |

---

## 🤖 Agent Workflow Guidelines

To maximize efficiency, include these guidelines in your agent's system prompt or custom instructions:

### 🐍 Workflow A: Single Scripts (PEP 723)
For simple, standalone tools, use PEP 723 inline metadata:
```python
# /// script
# dependencies = ["httpx", "pandas"]
# ///
import httpx
...
```
Execute using: `run_bash(command="uv run script.py")`.

### 📂 Workflow B: Complex Projects
For multi-file applications:
1. Initialize: `run_bash(command="uv init")`
2. Add dependencies: `run_bash(command="uv add <package>")`
3. Execute entry point: `run_bash(command="uv run <main_file>")`

---

## ⚙️ Configuration

The server supports the following environment variables (passed via Docker `--env`):

| Variable | Default | Description |
|---|---|---|
| `WORKSPACE_ROOT` | `/workspace` | Root directory for all sandboxed operations. |
| `COMMAND_TIMEOUT` | `30` | Default seconds before `run_bash` kills a process. |
| `MAX_SEARCH_RESULTS` | `50` | Maximum results returned by `search_workspace`. |
| `MAX_READ_SIZE_BYTES` | `1048576` | Maximum file size for `read_file` (1MB). |
| `LOG_LEVEL` | `INFO` | Python logging level (DEBUG, INFO, etc.). |

---

## 🛡️ Security Model

This server is designed with a **defense-in-depth** strategy:
- **Least Privilege**: The container runs as a non-root user (`mcpuser`).
- **Kernel Isolation**: Drops all Linux capabilities (`--cap-drop=ALL`).
- **Immutable Core**: The root filesystem is mounted read-only (`--read-only`).
- **Resource Quotas**: Memory and CPU caps prevent host system degradation.
- **Path Guard**: Boundary enforcement prevents path traversal attacks outside `/workspace`.
- **Ephemeral Sessions**: Containers are destroyed (`--rm`) immediately upon disconnection.

---

## 🤝 Contributing

1. **Install Dev Dependencies**: `uv sync`
2. **Run Linting**: `uv run ruff check .`
3. **Run Unit Tests**: `uv run pytest tests/ --ignore=tests/test_live_workflow.py`
4. **Run E2E Tests**: Set `OPENROUTER_API_KEY` and run `uv run pytest tests/test_live_workflow.py`

---
&copy; 2026 HrRodan. Licensed under [MIT](LICENSE).
