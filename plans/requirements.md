# Product Requirements Document (PRD): Sandboxed Agentic Workspace MCP Server

## 1. Executive Summary
A unified Model Context Protocol (MCP) server providing a highly secure, containerized workspace for Large Language Models (LLMs). By combining filesystem manipulation, bash command execution, and robust Python code execution (powered by `uv` and `ruff`), the server acts as an isolated "agentic playground" enabling autonomous coding, testing, and debugging without risking the host machine.

## 2. System Architecture & Lifecycle
* **Base Image:** `ghcr.io/astral-sh/uv:python3.14-trixie`. The Dockerfile must explicitly install `curl`, `git`, `jq`, `nano`, `patch`, and `ripgrep` via `apt-get` as they are not included in the slim/trixie base by default.
* **Communication Protocol:** JSON-RPC over Standard Input/Output (`stdio`) using the `fastmcp` PyPI package (FastMCP 3.x by jlowin, which offers better decorator semantics and spec coverage than the legacy 1.0 version bundled in the official `mcp` SDK).
* **Concurrency:** All tool functions must be implemented asynchronously (`async def`) using `asyncio` to prevent I/O blocking.
* **State Management:** The Docker container is ephemeral (`--rm`), destroyed upon client disconnection. However, it remains continuously active during the session.
* **Virtual Environment Isolation (CRITICAL):** While the `/workspace` directory is mounted from the host, the container's Python virtual environment (`.venv`) MUST NOT reside in `/workspace`. Writing `.venv` to the host volume leads to cross-OS binary pollution (e.g., Linux container binaries breaking a macOS host environment). The Dockerfile must set `UV_PROJECT_ENVIRONMENT=/opt/venv` or similar to keep dependencies strictly inside the container.

## 3. Security, Sandboxing & Resource Isolation
The system enforces strict isolation and prevents host resource exhaustion:
* **Host-to-Container UID/GID Mapping:** To ensure file permission parity, the container must run with the host user's permissions. Since MCP clients don't evaluate shell variables like `$(id -u)` in their JSON config arrays, the launch command must use a `bash -c` wrapper to evaluate these, or instruct the user to hardcode their UID.
* **Kernel Isolation:** Container execution must drop unnecessary capabilities (`--cap-drop=ALL`) and prevent privilege escalation (`--security-opt=no-new-privileges:true`).
* **Hardware Quotas:** Docker runtime flags must cap resources (e.g., `--memory="2g" --cpus="2.0"`) to prevent LLM-generated code from crashing the host.
* **Workspace Boundary & Path Traversal:** All operations are strictly confined to the `/workspace` mount. Tools must resolve absolute paths and explicitly block access outside this directory.
* **Execution Timeouts:** Bash commands and Python scripts must enforce timeouts. `run_bash` must allow at least 120 seconds for `uv sync` operations, while purely computational tools can use a stricter 30-second limit.

## 4. Tool Specifications (LLM API)
Following Pattern A ("One tool per action"), all tools must utilize **Pydantic** for input validation, return highly **actionable error messages**, and include explicit MCP capabilities annotations.

### 4.1 Execution & Environment Tools
* **`run_bash`** `(command: str)`
  * *Description:* Executes shell commands in `/workspace`. Primary vector for running `uv init`, `uv add`, `uv run`. Limit to 120s timeout.
  * *Annotation:* `destructiveHint: true`
* **`lint_workspace`** `(path: str = ".")`
  * *Description:* Proactively executes `ruff check <path>` and `ruff format --check <path>`.
  * *Implementation Note:* Ensure `ruff` is proactively installed in the Docker base image via `uv tool install ruff` to prevent repetitive downloads on every ephemeral container start.
  * *Annotation:* `readOnlyHint: true`

### 4.2 Standard Filesystem Tools
* **`read_file`** `(filepath: str)`: Returns file contents. (`readOnlyHint: true`)
* **`write_file`** `(filepath: str, content: str)`: Overwrites/creates a file, auto-creating missing parent directories. (`destructiveHint: true`)
* **`list_directory`** `(directory_path: str = ".")`: Returns contents tagged as `[FILE]` or `[DIR]`. (`readOnlyHint: true`)
* **`get_file_info`** `(filepath: str)`: Returns Size (bytes) and Last Modified timestamp. (`readOnlyHint: true`)
* **`search_workspace`** `(pattern: str)`: Uses `ripgrep` for ultra-fast, token-efficient workspace searches, truncated to 50 results. (`readOnlyHint: true`)

### 4.3 Advanced Editing Tool
* **`search_and_replace`** `(filepath: str, exact_search_block: str, replace_block: str)`
  * *Description:* Swaps a specific string block (highly token-efficient). *Warning: strict exact match means indentation errors from LLMs will cause failures. Prompt must heavily emphasize matching leading whitespace.*
  * *Validation Gate:* Edits are performed in-memory first. If a `.py` file, validates via `ast.parse()`. If a `.json` file, via `json.loads()`.
  * *Error Handling:* Rejects invalid syntax instantly, returning Error Type, Line Number, and Message to the LLM for self-correction without touching disk.
  * *Annotation:* `destructiveHint: true`

## 5. Code Quality & Project Structure
* **Strict Typing:** 100% type annotation coverage using standard Python type hints. Must pass `pyright` or `mypy` strict modes.
* **Docstrings:** All modules and functions must use Google-style docstrings. Tool docstrings must be exceptionally descriptive.
* **Extensible Structure:** Standard modern Python package format managed by `uv`:
  * `src/agent_workspace_mcp/` (contains `server.py`, `tools/`, `utils/`)
  * `tests/`
  * `pyproject.toml`, `Dockerfile`, `README.md`

## 6. Documentation & Client Configuration
The `README.md` must be comprehensive and include:
* **Host Setup:** Instructions for integrating with MCP clients like Claude Desktop.
* **Required Client JSON Schema:**
  *(Using `bash -c` to correctly evaluate the shell variables for UID/GID)*
  ```json
  {
    "mcpServers": {
      "agentic-workspace": {
        "command": "bash",
        "args": [
          "-c",
          "docker run -i --rm --memory=2g --cpus=2.0 --cap-drop=ALL --security-opt=no-new-privileges:true --env-file=.env --user $(id -u):$(id -g) -v <HOST_TARGET_DIRECTORY>:/workspace <BUILT_IMAGE_NAME>"
        ]
      }
    }
  }
  ```