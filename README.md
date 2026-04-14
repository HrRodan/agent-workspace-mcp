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
flowchart TD
    Client["MCP Client (Claude / Cursor)"] -- "stdio (JSON-RPC)" --> Server["FastMCP Server"]

    subgraph Sandbox ["Docker Sandbox (Isolated)"]
        direction TB
        Server -- "Subprocess" --> Bash["Bash / Shell"]
        Server -- "API" --> FS["Filesystem Utilities"]
        Server -- "Subprocess" --> UV["uv / Ruff / Python"]
    end

    FS -- "Mount" --> HostVolume["/workspace (Host Directory)"]
```

---

## 📦 Quick Start

### 1. Pull the Docker Image
```bash
docker pull ghcr.io/hrrodan/agent-workspace-mcp:latest
```
*(Alternatively, build locally: `docker build -t agent-workspace-mcp .`)*

### 2. Programmatic Usage (OpenAI Agents SDK)
Here is a quick boilerplate showing how to use the containerized workspace programmatically using the standard `openai-agents` SDK:

```python
import asyncio
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

async def main():
    # 1. Configure the MCP Server to run via Docker
    server = MCPServerStdio(
        name="Sandboxed Workspace",
        params={
            "command": "docker",
            "args": [
                "run", "-i", "--rm", "--init",
                "--memory=2g", "--cpus=2.0",
                "--pids-limit=256",
                "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
                "--read-only",
                "--tmpfs", "/tmp:size=64m",
                "--tmpfs", "/home/mcpuser/.cache:size=512m",
                "--user", "1000:1000", # Replace with your host UID:GID
                "-v", "/path/to/your/projects:/workspace",
                "ghcr.io/hrrodan/agent-workspace-mcp:latest",
            ],
        },
        client_session_timeout_seconds=60.0,
    )

    # 2. Attach server to the Agent
    agent = Agent(
        name="WorkspaceAgent",
        instructions="You are a coding agent with access to a secure workspace. Use your tools to manage files and run bash commands.",
        mcp_servers=[server],
    )

    # 3. Execute a workflow
    async with server:
        result = await Runner.run(
            agent, 
            "Create a python script in the workspace to print the first 10 Fibonacci numbers, then run it."
        )
        print(f"Agent's Final Output:\n{result.final_output}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Use with MCP Clients (Claude / Cursor)
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
        "--user", "1000:1000",
        "-v", "/path/to/your/projects:/workspace",
        "ghcr.io/hrrodan/agent-workspace-mcp:latest"
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

This server is designed with a **defense-in-depth** strategy, providing multiple layers of isolation and protection:

### 🐋 Container-Level Security
- **Non-Root Execution**: The container runs under a dedicated `mcpuser` (UID 1000).
- **Kernel Hardening**: All Linux capabilities are dropped (`--cap-drop=ALL`).
- **Privilege Lockdown**: Prevents processes from gaining new privileges (`no-new-privileges:true`).
- **Immutable Core**: The root filesystem is mounted **read-only** (`--read-only`).
- **Resource Quotas**: Hard limits on CPU, Memory, and PIDs prevent fork-bombs and host exhaustion.
- **Ephemeral Sessions**: Containers are strictly ephemeral (`--rm`), ensuring no state survives between connections.

### 🛡️ Application-Level Security
- **Path Guard**: Strict boundary enforcement prevents path traversal attacks outside `/workspace`.
- **Command Control**: Mandatory timeouts (default 60s) and process group isolation capture and kill orphan processes.
- **AST Validation**: `search_and_replace` validates Python, JSON, and TOML syntax in-memory before writing any changes.
- **Atomic Operations**: File edits use temp-and-move logic to prevent filesystem corruption during power-loss or crashes.
- **Size Enforcement**: Hard limits on file reads (1MB) and command outputs (50KB) protect against memory-overload attacks.

### 📊 Observability & Auditing
- **Real-time Logging**: All tool invocations are logged directly to the MCP client for immediate operator visibility.
- **Sanitized Errors**: Internal system paths and stack traces are suppressed in tool outputs to prevent information leakage.
- **Search Exclusions**: High-noise or sensitive directories (`.git`, `.venv`) are automatically excluded from search tools.

---

## 🤝 Contributing

1. **Install Dev Dependencies**: `uv sync`
2. **Run Linting**: `uv run ruff check .`
3. **Run Unit Tests**: `uv run pytest tests/ --ignore=tests/integration/`
4. **Run Integration Tests**: Set `OPENROUTER_API_KEY` and run `uv run pytest tests/integration/`

---
&copy; 2026 HrRodan. Licensed under [MIT](LICENSE).
