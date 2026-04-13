# Product Requirements Document (PRD): Sandboxed Agent Workspace MCP Server

## 1. Executive Summary
A unified Model Context Protocol (MCP) server providing a highly secure, containerized workspace for Large Language Models (LLMs). By combining filesystem manipulation, bash command execution, and robust Python code execution (powered by `uv` and `ruff`), the server acts as an isolated "agentic playground" enabling autonomous coding, testing, and debugging without risking the host machine.

## 2. System Architecture & Lifecycle
* **Base Image:** `ghcr.io/astral-sh/uv:python3.14-trixie`. Includes basic network access to fetch PyPI packages and essential utilities: `curl`, `git`, `jq`, `nano`, and `patch`.
* **Communication Protocol:** JSON-RPC over Standard Input/Output (`stdio`) using jlowin's `fastmcp` (FastMCP 3.x) rather than the generic SDK to leverage decorator-based clean tooling without boilerplate.
* **Concurrency:** All tool functions must be implemented asynchronously (`async def`) using `asyncio` to prevent I/O blocking.
* **State Management:** The Docker container is ephemeral and destroyed upon client disconnection (`--rm` flag). However, it remains continuously active during the session. All workspace state (including virtual environments) persists on the host-mounted volume. To ensure host macOS/Windows environments don't conflict with Linux `.venv` binaries, `UV_PROJECT_ENVIRONMENT=/workspace/.venv_container` should be designated.

## 3. Security, Sandboxing & Resource Isolation
The system enforces strict isolation and prevents host resource exhaustion:
* **Host-to-Container UID/GID Mapping:** To ensure file permission parity on Linux, the container must run with the host user's exact permissions. **Crucial Note:** Claude Desktop does not evaluate bash variables like `$(id -u)` in the JSON `args` array. Users must explicitly hardcode their UID (e.g., `--user 1000:1000`) in `server.json` or use an intermediate wrapper script. macOS/Windows Docker Desktop handles permissions transparently.
* **Non-Root Execution:** The Dockerfile must create and utilize a dedicated non-root user (`mcpuser`).
* **Kernel Isolation:** Container execution must drop all capabilities (`--cap-drop=ALL`) and prevent privilege escalation (`--security-opt=no-new-privileges:true`).
* **Hardware Quotas:** Docker runtime flags must cap resources (e.g., `--memory="2g" --cpus="2.0"`) to prevent LLM-generated code from crashing the host.
* **Workspace Boundary & Path Traversal:** All operations are strictly confined to a host directory mapped to `/workspace`. Tools must resolve absolute paths and explicitly block access outside `/workspace`.
* **Network Isolation:** Outbound network access is unrestricted to allow agents to fetch PyPI packages and external resources. No incoming ports are exposed.
* **Execution Timeouts:** Bash commands and Python scripts must enforce a strict 30-second timeout to prevent infinite loops from hanging the `stdio` stream.

## 4. Tool Specifications (LLM API)
All tools must utilize **Pydantic** for input validation, return highly **actionable error messages** (guiding the LLM on how to fix mistakes), and use FastMCP's built-in docstring parsing to automatically generate description schemas.

### 4.1 Execution & Environment Tools
* **`run_bash`** `(command: str)`
  * *Description:* Executes shell commands in `/workspace`. Primary vector for running `uv init`, `uv add`, `uv run`, and applying `patch` diffs.
  * *Implementation:* Must use `asyncio.create_subprocess_shell` with a strict `asyncio.wait_for` timeout.
* **`lint_workspace`** `(path: str = ".")`
  * *Description:* Proactively executes `uvx ruff check <path>` and `uvx ruff format --check <path>`.

### 4.2 Standard Filesystem Tools
* **`read_file`** `(filepath: str)`: Returns file contents.
* **`write_file`** `(filepath: str, content: str)`: Overwrites/creates a file, auto-creating missing parent directories.
* **`list_directory`** `(directory_path: str = ".")`: Returns contents tagged as `[FILE]` or `[DIR]`.
* **`get_file_info`** `(filepath: str)`: Returns Size (bytes) and Last Modified timestamp.
* **`search_workspace`** `(pattern: str)`: Glob search (e.g., `**/*.py`), truncated to 50 results to protect token limits.

### 4.3 Advanced Editing Tools
* **`apply_patch`** `(patch_content: str)`
  * *Description:* Applies a Unified Diff (`.patch` format) to the workspace using the native `patch` utility.
  * *Implementation:* Writes the diff to a temporary file and executes `patch -p1 < temp.patch` via `run_bash`.
* **`search_and_replace`** `(filepath: str, exact_search_block: str, replace_block: str)`
  * *Description:* Swaps a specific string block (highly token-efficient). Agent should be prompted to use `read_file` first to ensure perfect whitespace matching.
  * *Validation Gate:* Edits are performed in-memory first. If a `.py` file, it validates via `ast.parse()`. If a `.json` file, via `json.loads()`.
  * *Error Handling:* Rejects invalid syntax instantly, returning the specific Error Type, Line Number, and Message to the LLM to facilitate self-correction without touching the disk.

## 5. Code Quality & Project Structure
* **Strict Typing:** 100% type annotation coverage using standard Python type hints. Must pass `pyright` or `mypy` under strict mode.
* **Docstrings:** All modules and functions must use Google-style or NumPy-style docstrings. Tool docstrings must be exceptionally descriptive to guide LLM behavior.
* **Extensible Structure:** Standard modern Python package format managed by `uv`:
  * `src/agent_workspace_mcp/` (contains `server.py`, `tools/`, `utils/`)
  * `tests/`
  * `pyproject.toml`, `server.json`, `Dockerfile`, `README.md`

## 6. Documentation & Client Configuration
The `README.md` must be comprehensive and include:
* **System Prompt Guidelines (Agent Workflows):** Explicit instructions for users to pass to their agents:
  * *Workflow A (Single Scripts):* Use PEP 723 inline metadata (`# /// script`) for single files and execute via `uv run`.
  * *Workflow B (Complex Projects):* Use `run_bash` for `uv init`, build multi-file structures, and manage dependencies via `uv add`.
* **Host Setup:** Instructions and JSON snippets for integrating with MCP clients (Claude Desktop, Cursor). Crucially avoids importing the host's `.env` file to prevent the LLM agent from obtaining unrestricted access to host secrets.

```json
{
  "mcpServers": {
    "agent-workspace-mcp": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "--memory=2g", "--cpus=2.0",
        "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
        "--env", "UV_PROJECT_ENVIRONMENT=/workspace/.venv_container",
        "--user", "1000:1000",
        "-v", "<HOST_TARGET_DIRECTORY>:/workspace",
        "<BUILT_IMAGE_NAME>"
      ]
    }
  }
}
```
*Note: Hardcode your host system UID:GID instead of `1000:1000` if you are on Linux and it differs from 1000. Claude Desktop will NOT evaluate bash variables directly inside the JSON array.*

## 7. Testing Strategy
* **Unit Testing:** Validate path boundary logic (`safe_path`), AST validation, and input parsing using mocked filesystem operations.
* **E2E Agentic Testing:** Pytest suite utilizing `litellm` and OpenRouter (via `DEFAULT_MODEL` falling back to `openrouter/google/gemini-3-flash-preview`) to test real LLM agent logic directly interacting with the running Docker container over `stdio`.
  * *Scenario 1:* Validate LLM can create a standalone Python file with PEP 723 dependencies and execute it.
  * *Scenario 2:* Validate LLM can initialize a project (`uv init`), add dependencies (`uv add`), and execute the entry point.
  * *Scenario 3:* Validate LLM can utilize `run_bash` to execute Linux tools (e.g., `grep` for string searching, `jq` for json parsing).
  * *Scenario 4:* Validate LLM can isolate syntax errors using `lint_workspace` and securely apply targeted fixes via `search_and_replace`.

## 8. Logging & Observability Strategy
Because the server communicates over `stdio`, `stdout` corruption must be strictly prevented.
* **Protocol Safety:** Absolutely no `print()` statements. Third-party library `stdout` must be suppressed.
* **Native MCP Logging:** Use `FastMCP` Context (`ctx.info()`, `ctx.error()`) to stream real-time execution logs directly to the MCP client UI.
* **Persistent Diagnostic Logging:** Use Python's `logging` module to maintain a persistent audit trail written to a hidden mounted directory (e.g., `/workspace/.mcp/server.log`). A `StreamHandler` must concurrently route to `sys.stderr`.
* **Agent-Driven Audit Logging:** System prompts should instruct the agent to use `run_bash` (`echo "step X" >> run.log`) to record its own progress during long workflows.

## 9. CI/CD & MCP Registry Publishing Constraints
* **GitHub Actions Workflow:**
  * Enforce PR linting/typing checks (`ruff`, `pyrefly`).
  * Automate Docker image build/push to GHCR on `main` commits.
  * Automate official MCP Registry publishing via the `mcp-publisher` CLI (`login github` -> `publish`).
  * Scheduled cron job (weekly) to automatically rebuild and push the Docker image to absorb upstream `uv` base image security patches.

### 9.1 Required Registry Artifacts

**`Dockerfile`**
```dockerfile
FROM ghcr.io/astral-sh/uv:python3.14-trixie

# Label for discoverability
LABEL io.modelcontextprotocol.server.name="io.github.HrRodan/agent-workspace-mcp"

# Install minimal system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    nano \
    patch \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group with an explicit UID for Linux compatibility
RUN groupadd -g 1000 mcpuser && useradd -u 1000 -g 1000 -m mcpuser

# Setup workspace and permissions
RUN mkdir -p /workspace && chown mcpuser:mcpuser /workspace
WORKDIR /workspace

# Set environments to avoid polluting host machine's .venv via mounts
ENV UV_PROJECT_ENVIRONMENT=/workspace/.venv_container

# Install the dependencies using FastMCP 3.x globally via uv
RUN uv pip install --system fastmcp pydantic

# Copy the server application code
COPY src/ /app/src/
COPY pyproject.toml /app/

# Switch to the non-root user before executing
USER mcpuser

# Execute the FastMCP server directly, wrapped by `tini` to properly reap zombie subprocesses
ENTRYPOINT ["tini", "--", "python", "-m", "agent_workspace_mcp.server"]
```

**`server.json`**
```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-10-17/server.schema.json",
  "name": "io.github.HrRodan/agent-workspace-mcp",
  "title": "Agent Workspace MCP",
  "description": "A sandboxed, agentic workspace providing secure filesystem, bash, and uv-powered Python execution.",
  "version": "1.0.0",
  "packages": [
    {
      "registryType": "oci",
      "identifier": "ghcr.io/HrRodan/agent-workspace-mcp:1.0.0",
      "transport": {
        "type": "stdio"
      }
    }
  ]
}
```