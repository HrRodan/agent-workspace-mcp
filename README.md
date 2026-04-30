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
- ⚡ **Precision Editing**: Advanced `search_and_replace` with **fuzzy whitespace matching**, **indentation preservation**, dry-run support, and syntax validation for Python, JSON, JSONL, TOML, and YAML.
- **📊 Real-time Observability**: Direct logging to MCP client UI and persistent rotating audit logs.

---

## 🏗️ Architecture

```mermaid
flowchart TD
    Client["MCP Client (Claude / Cursor)"] -- "stdio (JSON-RPC)" --> FastMCP["FastMCP Server"]

    subgraph Sandbox ["Docker Sandbox Container (mcpuser)"]
        direction TB
        
        FastMCP -. "Intercepts accidental prints" .-> StdioGuard["StdoutRedirector"]
        FastMCP -. "Application Logs" .-> Logger["Dual Logger (stderr & .mcp/server.log)"]
        
        FastMCP -- "Tool Calls" --> SecurityGuard["Security & Path Validator"]
        
        subgraph Toolset ["Tool Modules"]
            direction TB
            SecurityGuard --> FSTools["Filesystem (read, write, list, search)"]
            SecurityGuard --> EditTools["Editing (search_and_replace)"]
            SecurityGuard --> ExecTools["Execution (run_bash)"]
        end

        EditTools -- "AST Verification" --> Validator["Syntax Validations (Python, JSON, JSONL, TOML, YAML)"]
        ExecTools -- "Process Group (Timeout=60s)" --> Shell["/bin/sh Subprocess"]
        Shell -- "Package Mgt & Checks" --> UV["uv Environment / Ruff"]
        
        FSTools -- "Secure I/O" --> Workspace["/workspace Directory"]
        EditTools -- "Atomic Writes" --> Workspace
        Shell -- "Executes within" --> Workspace
    end

    Workspace <--"Volume Mount"--> HostFS["User Host Filesystem"]
```

---

## 📦 Quick Start

### 1. Pull or Build the Docker Image
```bash
# Pull from GHCR
docker pull ghcr.io/hrrodan/agent-workspace-mcp:latest

# OR: Build locally with your host's UID/GID for optimal permissions
docker build --build-arg UID=$(id -u) --build-arg GID=$(id -g) -t agent-workspace-mcp .
```

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
                # "--network", "none", # Network Isolation (optional) - see below
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

    # 2. Attach server to the Agent and load the skill instructions (optional)
    with open("skills/agent-workspace-mcp/SKILL.md", "r") as f:
        skill_instructions = f.read()

    agent = Agent(
        name="WorkspaceAgent",
        instructions=f"You are a coding agent with access to a secure workspace.\n\n{skill_instructions}",
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
        // "--network", "none", // Network Isolation (optional) - see below
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
| `read_file` | Read text files with optional `offset` and `limit` (default: 100 lines). |
| `write_file` | Create files with **syntax validation** and a **5MB size guard**. Refuses to overwrite existing files by default (`create_only=True`). |
| `list_directory` | List contents with `[F]`ile and `[D]`irectory prefixes. |
| `search_workspace` | Find files by glob pattern with support for `exclude_patterns`. |
| `run_bash` | Execute shell commands in `/workspace` with a 60s timeout. |
| `search_and_replace` | Multi-edit tool with **fuzzy whitespace matching**, **indentation preservation**, dry-run mode, and **syntax validation (Python, JSON, JSONL, TOML, YAML)**. |

---

## ⚙️ Configuration

The server supports the following environment variables (passed via Docker `--env`):

| Variable | Default | Description |
|---|---|---|
| `COMMAND_TIMEOUT` | `60` | Default seconds before `run_bash` kills a process. |
| `MAX_SEARCH_RESULTS` | `50` | Maximum results returned by `search_workspace`. |
| `MAX_READ_SIZE_BYTES` | `1048576` | Maximum file size for `read_file` (1MB). |
| `MAX_WRITE_SIZE_BYTES` | `5242880` | Maximum file size for `write_file` (5MB). |
| `LOG_LEVEL` | `INFO` | Python logging level (DEBUG, INFO, etc.). |

---

## 🛡️ Security & Architecture Model

This server employs a **defense-in-depth** strategy, explicitly separating strict security boundaries from developer experience and operational reliability features.

### 🔒 Core Security Features
These features are designed to protect the host system and enforce strict isolation boundaries.

- **Kernel Hardening**: All Linux capabilities are dropped (`--cap-drop=ALL`), neutralizing privilege escalation vectors.
- **Immutable Server Code**: The `/app` directory containing the server source and its virtual environment is owned by `root` and read-only for the `mcpuser`. This prevents the server from modifying itself or being tampered with via `run_bash`.
- **Privilege Lockdown**: Enforces `no-new-privileges:true` to prevent any process from gaining elevated rights.
- **Immutable System Core**: The container's root filesystem is mounted entirely **read-only**, providing a second layer of defense against OS-level tampering.
- **Resource Quotas**: Hard limitations on CPU, Memory, and PIDs mitigate denial-of-service (DoS) attempts like fork-bombs and host exhaustion.
- **Strict Boundary Enforcement**: A robust path validator comprehensively blocks all path traversal attacks outside the designated `/workspace`.
- **Process & Resource Control**: Mandatory command timeouts (default 60s) and strict process group isolation ensure runaway or malicious processes are killed.
- **Memory-Overload Protection**: Hard limits on file reads (1MB) and command outputs (50KB) prevent memory exhaustion.
- **Information Leakage Prevention**: Internal stack traces and system paths are suppressed and sanitized from tool outputs.

### 🛠️ Developer Experience & Convenience
Features focused on seamless integration, usability, and reducing friction during agentic workflows.

- **Host-Aligned Non-Root Identity**: Runs as `mcpuser` with UID/GID [customizable at build time](#1-pull-or-build-the-docker-image), eliminating tedious file permission conflicts on host volume mounts.
- **Intelligent Search Exclusions**: High-noise or sensitive directories (`.git`, `.venv`) are automatically ignored to keep context windows lean and relevant.
- **Ephemeral Workspaces**: Containers are strictly ephemeral (`--rm`), guaranteeing a clean, predictable slate for every new session without state leaking across connections.
- **Standardized Discovery**: Complies with the [OCI Image Specification](https://github.com/opencontainers/image-spec) for standardized container ecosystem integration and transparent auditing.

### ⚙️ Reliability & Safety Mechanisms
Features ensuring the structural integrity of the workspace and providing observability.

- **Pre-Write Syntax Validation**: Both `write_file` and `search_and_replace` perform in-memory syntax validation for Python, JSON, JSONL, TOML, and YAML before persisting changes, preventing broken code states.
- **Fail-Safe Writing**: `write_file` blocks accidental overwrites of existing files by default and enforces a 5MB size guard to prevent workspace flooding.
- **Atomic File Operations**: Edits utilize temp-and-move logic to guarantee file integrity and prevent corruption, even during unexpected interruptions or crashes.
- **Transparent Observability**: All tool invocations and state changes are streamed in real-time to the MCP client UI for immediate operator oversight.

### 🌐 Network Isolation (Optional)

By default, the container has full network access via Docker's `bridge` network. For maximum isolation, you can completely disable the network stack using `--network none`:

```bash
docker run -i --rm --init \
  --network none \
  --memory=2g --cpus=2.0 --pids-limit=256 \
  --cap-drop=ALL --security-opt=no-new-privileges:true \
  --read-only \
  --tmpfs /tmp:size=64m \
  --tmpfs /home/mcpuser/.cache:size=512m \
  --user 1000:1000 \
  -v /path/to/your/projects:/workspace \
  ghcr.io/hrrodan/agent-workspace-mcp:latest
```

This creates a fully **air-gapped sandbox** — only the loopback interface exists inside the container. All outbound connections (`curl`, DNS, `uv add`, etc.) will fail immediately, eliminating data exfiltration and lateral movement risks entirely.

> [!NOTE]
> With `--network none`, the agent cannot install packages at runtime. All dependencies must be pre-installed in a custom image or pre-populated in the mounted workspace volume.

---

## 🤝 Contributing

1. **Install Dev Dependencies**: `uv sync`
2. **Run Linting**: `uv run ruff check .`
3. **Run Unit Tests**: `uv run pytest tests/ --ignore=tests/integration/`
4. **Run Integration Tests**: Set `OPENROUTER_API_KEY` and run `uv run pytest tests/integration/`

---
&copy; 2026 HrRodan. Licensed under [MIT](LICENSE).
