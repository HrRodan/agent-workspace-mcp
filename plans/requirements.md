# Product Requirements Document (PRD): Sandboxed Agentic Workspace MCP Server

## 1. Executive Summary
A unified Model Context Protocol (MCP) server providing a highly secure, containerized workspace for Large Language Models (LLMs). By combining filesystem manipulation, bash command execution, and robust Python code execution (powered by `uv` and `ruff`), the server acts as an isolated "agentic playground" enabling autonomous coding, testing, and debugging without risking the host machine.

## 2. System Architecture & Lifecycle
* **Base Image:** `ghcr.io/astral-sh/uv:python3.14-trixie`. Includes basic network access to fetch PyPI packages and essential utilities: `curl`, `git`, `jq`, `nano`, and `patch`.
* **Communication Protocol:** JSON-RPC over Standard Input/Output (`stdio`) using the official Python `mcp` SDK (`FastMCP`).
* **Concurrency:** All tool functions must be implemented asynchronously (`async def`) using `asyncio` to prevent I/O blocking.
* **State Management:** The Docker container is ephemeral and destroyed upon client disconnection (`--rm` flag). However, it remains continuously active during the session. All workspace state (including `.venv` directories) persists on the host-mounted volume.

## 3. Security, Sandboxing & Resource Isolation
The system enforces strict isolation and prevents host resource exhaustion:
* **Host-to-Container UID/GID Mapping:** To ensure file permission parity, the container must run with the host user's exact permissions using `--user $(id -u):$(id -g)`.
* **Non-Root Execution:** The Dockerfile must create and utilize a dedicated non-root user (`mcpuser`).
* **Kernel Isolation:** Container execution must drop all capabilities (`--cap-drop=ALL`) and prevent privilege escalation (`--security-opt=no-new-privileges:true`).
* **Hardware Quotas:** Docker runtime flags must cap resources (e.g., `--memory="2g" --cpus="2.0"`) to prevent LLM-generated code from crashing the host.
* **Workspace Boundary & Path Traversal:** All operations are strictly confined to a host directory mapped to `/workspace`. Tools must resolve absolute paths and explicitly block access outside `/workspace`.
* **Execution Timeouts:** Bash commands and Python scripts must enforce a strict 30-second timeout to prevent infinite loops from hanging the `stdio` stream.

## 4. Tool Specifications (LLM API)
All tools must utilize **Pydantic** for input validation, return highly **actionable error messages** (guiding the LLM on how to fix mistakes), and include explicit MCP capabilities annotations.

### 4.1 Execution & Environment Tools
* **`run_bash`** `(command: str)`
  * *Description:* Executes shell commands in `/workspace`. Primary vector for running `uv init`, `uv add`, `uv run`, and applying `patch` diffs.
  * *Annotation:* `destructiveHint: true`
* **`lint_workspace`** `(path: str = ".")`
  * *Description:* Proactively executes `uvx ruff check <path>` and `uvx ruff format --check <path>`.
  * *Annotation:* `readOnlyHint: true`

### 4.2 Standard Filesystem Tools
* **`read_file`** `(filepath: str)`: Returns file contents. (`readOnlyHint: true`)
* **`write_file`** `(filepath: str, content: str)`: Overwrites/creates a file, auto-creating missing parent directories. (`destructiveHint: true`)
* **`list_directory`** `(directory_path: str = ".")`: Returns contents tagged as `[FILE]` or `[DIR]`. (`readOnlyHint: true`)
* **`get_file_info`** `(filepath: str)`: Returns Size (bytes) and Last Modified timestamp. (`readOnlyHint: true`)
* **`search_workspace`** `(pattern: str)`: Glob search (e.g., `**/*.py`), truncated to 50 results to protect token limits. (`readOnlyHint: true`)

### 4.3 Advanced Editing Tool
* **`search_and_replace`** `(filepath: str, exact_search_block: str, replace_block: str)`
  * *Description:* Swaps a specific string block (highly token-efficient).
  * *Validation Gate:* Edits are performed in-memory first. If a `.py` file, it validates via `ast.parse()`. If a `.json` file, via `json.loads()`.
  * *Error Handling:* Rejects invalid syntax instantly, returning the specific Error Type, Line Number, and Message to the LLM to facilitate self-correction without touching the disk.
  * *Annotation:* `destructiveHint: true`

## 5. Code Quality & Project Structure
* **Strict Typing:** 100% type annotation coverage using standard Python type hints. Must pass `pyright` or `mypy` under strict mode.
* **Docstrings:** All modules and functions must use Google-style or NumPy-style docstrings. Tool docstrings must be exceptionally descriptive to guide LLM behavior.
* **Extensible Structure:** Standard modern Python package format managed by `uv`:
  * `src/agent_workspace_mcp/` (contains `server.py`, `tools/`, `utils/`)
  * `tests/`
  * `pyproject.toml`, `server.json`, `Dockerfile`, `README.md`

## 6. Documentation & Client Configuration
The `README.md` must be comprehensive and include:
* **Host Setup:** Instructions and JSON copy-paste snippets for integrating with MCP clients (Claude Desktop, Cursor). Includes env var passing (`--env-file=.env`).
* **Required Client JSON Schema:**
  ```json
  {
    "mcpServers": {
      "agentic-workspace": {
        "command": "docker",
        "args": [
          "run", "-i", "--rm",
          "--memory=2g", "--cpus=2.0",
          "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
          "--env-file=.env",
          "--user", "$(id -u):$(id -g)",
          "-v", "<HOST_TARGET_DIRECTORY>:/workspace",
          "<BUILT_IMAGE_NAME>"
        ]
      }
    }
  }