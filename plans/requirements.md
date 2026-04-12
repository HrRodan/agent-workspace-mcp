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
  * `src/mcp_agentic_workspace/` (contains `server.py`, `tools/`, `utils/`)
  * `tests/`
  * `pyproject.toml`, `server.json`, `Dockerfile`, `README.md`

## 6. Documentation & Client Configuration
The `README.md` must be comprehensive and include:
* **System Prompt Guidelines (Agent Workflows):** Explicit instructions for users to pass to their agents:
  * *Workflow A (Single Scripts):* Use PEP 723 inline metadata (`# /// script`) for single files and execute via `uv run`.
  * *Workflow B (Complex Projects):* Use `run_bash` for `uv init`, build multi-file structures, and manage dependencies via `uv add`.
* **Host Setup:** Instructions and JSON snippets for integrating with MCP clients (Claude Desktop, Cursor). Includes env var passing (`--env-file=.env`).

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
```

## 7. Testing Strategy
* **Unit Testing:** Validate path boundary logic (`safe_path`), AST validation, and input parsing using mocked filesystem operations.
* **E2E Agentic Testing:** Pytest suite utilizing OpenAI/Anthropic SDKs to test real LLM reasoning against the running container.
  * *Scenario 1:* Validate LLM can create a standalone Python file with PEP 723 dependencies and execute it.
  * *Scenario 2:* Validate LLM can initialize a project (`uv init`), add dependencies (`uv add`), and execute the entry point.

## 8. Logging & Observability Strategy
Because the server communicates over `stdio`, `stdout` corruption must be strictly prevented.
* **Protocol Safety:** Absolutely no `print()` statements. Third-party library `stdout` must be suppressed.
* **Native MCP Logging:** Use `FastMCP` Context (`ctx.info()`, `ctx.error()`) to stream real-time execution logs directly to the MCP client UI.
* **Persistent Diagnostic Logging:** Use Python's `logging` module to maintain a persistent audit trail written to a hidden mounted directory (e.g., `/workspace/.mcp/server.log`). A `StreamHandler` must concurrently route to `sys.stderr`.
* **Agent-Driven Audit Logging:** System prompts should instruct the agent to use `run_bash` (`echo "step X" >> run.log`) to record its own progress during long workflows.

## 9. CI/CD & MCP Registry Publishing Constraints
* **GitHub Actions Workflow:**
  * Enforce PR linting/typing checks (`ruff`, `mypy`).
  * Automate Docker image build/push to GHCR on `main` commits.
  * Automate official MCP Registry publishing via the `mcp-publisher` CLI (`login github` -> `publish`).
  * Scheduled cron job (weekly) to automatically rebuild and push the Docker image to absorb upstream `uv` base image security patches.

### 9.1 Required Registry Artifacts

**`Dockerfile`**
```dockerfile
FROM ghcr.io/astral-sh/uv:python3.14-trixie

# Label for official MCP Registry discoverability
LABEL io.modelcontextprotocol.server.name="io.github.yourusername/agentic-workspace"

# Install minimal system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    nano \
    patch \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group
RUN groupadd -r mcpuser && useradd -r -g mcpuser -m mcpuser

# Setup workspace and permissions
RUN mkdir -p /workspace && chown mcpuser:mcpuser /workspace
WORKDIR /workspace

# Install the MCP SDK and dependencies globally via uv
RUN uv pip install --system mcp[cli] pydantic

# Copy the server application code
COPY src/ /app/src/
COPY pyproject.toml /app/

# Switch to the non-root user before executing
USER mcpuser

# Execute the FastMCP server
ENTRYPOINT ["uv", "run", "--directory", "/app", "python", "-m", "mcp_agentic_workspace.server"]
```

**`server.json`**
```json
{
  "$schema": "[https://static.modelcontextprotocol.io/schemas/2025-07-09/server.schema.json](https://static.modelcontextprotocol.io/schemas/2025-07-09/server.schema.json)",
  "name": "io.github.yourusername/agentic-workspace",
  "description": "A sandboxed, agentic workspace providing secure filesystem, bash, and uv-powered Python execution.",
  "version": "1.0.0",
  "packages": [
    {
      "registry_type": "oci",
      "registry_base_url": "[https://ghcr.io](https://ghcr.io)",
      "identifier": "yourusername/agentic-workspace",
      "version": "1.0.0"
    }
  ]
}
```