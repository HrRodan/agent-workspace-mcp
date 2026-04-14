# Product Requirements Document (PRD): Sandboxed Agent Workspace MCP Server

## 1. Executive Summary
A unified Model Context Protocol (MCP) server providing a highly secure, containerized workspace for Large Language Models (LLMs). By combining filesystem manipulation, bash command execution, and robust Python code execution (powered by `uv` and `ruff`), the server acts as an isolated "agentic playground" enabling autonomous coding, testing, and debugging without risking the host machine.

## 2. System Architecture & Lifecycle
* **Base Image:** `ghcr.io/astral-sh/uv:python3.14-trixie`. Includes basic network access to fetch PyPI packages and essential utilities: `curl`, `git`, `jq`, `nano`, and `patch`.
* **Communication Protocol:** JSON-RPC over Standard Input/Output (`stdio`) using jlowin's `fastmcp` (FastMCP 3.x, currently `>=3.2.3`) rather than the generic SDK to leverage decorator-based clean tooling without boilerplate.
* **Concurrency:** All tool functions must be implemented asynchronously (`async def`) using `asyncio` to prevent I/O blocking.
* **State Management:** The Docker container is ephemeral and destroyed upon client disconnection (`--rm` flag). However, it remains continuously active during the session. All workspace state (including virtual environments) persists on the host-mounted volume. To ensure host macOS/Windows environments don't conflict with Linux `.venv` binaries, `UV_PROJECT_ENVIRONMENT=/workspace/.venv_container` should be designated.
* **Signal Handling & Graceful Shutdown:** The server must handle `SIGTERM` and `SIGINT` gracefully. On receiving a termination signal, it must cancel any running subprocesses spawned by `run_bash`, flush log buffers, and exit cleanly. `tini` serves as PID 1 and handles signal forwarding and zombie reaping.

## 3. Configuration & Environment Variables
The server's behavior must be configurable via environment variables with sensible defaults:

| Variable | Default | Description |
|---|---|---|
| `WORKSPACE_ROOT` | `/workspace` | Root directory for all sandboxed operations. |
| `UV_PROJECT_ENVIRONMENT` | `/workspace/.venv_container` | Isolates container venv from host venv. |
| `COMMAND_TIMEOUT` | `30` | Seconds before `run_bash` / `apply_patch` kills a subprocess. |
| `MAX_SEARCH_RESULTS` | `50` | Ceiling for `search_workspace` glob output. |
| `MAX_READ_SIZE_BYTES` | `1048576` (1 MB) | Maximum file size `read_file` will return inline. |
| `LOG_LEVEL` | `INFO` | Python `logging` level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

## 4. Security, Sandboxing & Resource Isolation
The system enforces strict isolation and prevents host resource exhaustion:
* **Host-to-Container UID/GID Mapping:** To ensure file permission parity on Linux, the container must run with the host user's exact permissions. **Crucial Note:** Claude Desktop does not evaluate bash variables like `$(id -u)` in the JSON `args` array. Users must explicitly hardcode their UID (e.g., `--user 1000:1000`) in `server.json` or use an intermediate wrapper script. macOS/Windows Docker Desktop handles permissions transparently.
* **Non-Root Execution:** The Dockerfile must create and utilize a dedicated non-root user (`mcpuser`).
* **Kernel Isolation:** Container execution must drop all capabilities (`--cap-drop=ALL`) and prevent privilege escalation (`--security-opt=no-new-privileges:true`). Note: `fork()` and `execve()` are fundamental system calls that do **not** require elevated Linux capabilities; `--cap-drop=ALL` will NOT prevent subprocess creation. This setup is fully compatible with `asyncio.create_subprocess_exec` and `tini`.
* **Filesystem Hardening:** The container root filesystem should be mounted read-only (`--read-only`) with `tmpfs` mounts for `/tmp` and `/home/mcpuser/.cache` (for `uv` cache writes). This prevents the agent from writing outside `/workspace` or modifying system files. The `/workspace/.mcp/` directory is used for server logs.
* **Process Limits:** Use `--pids-limit=256` to prevent fork bomb attacks from LLM-generated code.
* **Hardware Quotas:** Docker runtime flags must cap resources (e.g., `--memory="2g" --cpus="2.0"`) to prevent LLM-generated code from crashing the host.
* **Workspace Boundary & Path Traversal:** All operations are strictly confined to a host directory mapped to `/workspace`. The `safe_path` utility must:
  1. Resolve the target path to an absolute path.
  2. Call `Path.resolve(strict=False)` (to resolve `..` and symlinks even if the target doesn't yet exist).
  3. Verify via `Path.is_relative_to(WORKSPACE_ROOT)`.
  4. **Symlink Attack Defense:** After resolution, if the final path resides outside `WORKSPACE_ROOT`, the operation is blocked regardless of how many symlink hops occurred.
* **Network Isolation:** Outbound network access is unrestricted to allow agents to fetch PyPI packages and external resources. No incoming ports are exposed.
* **Execution Timeouts:** Bash commands and Python scripts must enforce a configurable timeout (`COMMAND_TIMEOUT`, default 30s) to prevent infinite loops from hanging the `stdio` stream.

## 5. Tool Specifications (LLM API)
All tools must utilize **Pydantic** (via `Annotated[..., Field(...)]`) for input validation, return highly **actionable error messages** (guiding the LLM on how to fix mistakes), and use FastMCP's built-in docstring parsing to automatically generate description schemas.

**Error Handling Contract:** Every tool must categorize errors and return structured messages:
* **Boundary Violation:** `"ERROR: Path '/../../etc/passwd' resolves outside /workspace. Use paths relative to /workspace."`
* **File Not Found:** `"ERROR: File 'main.py' not found. Use list_directory() to discover available files."`
* **Timeout:** `"ERROR: Command timed out after 30s. Simplify the command or break it into smaller steps."`
* **Validation Failure:** `"ERROR: Python syntax error at line 15: unexpected indent. Fix the indentation before retrying."`

### 5.1 Execution & Environment Tools
* **`run_bash`** `(command: str, timeout: int = COMMAND_TIMEOUT)`
  * *Description:* Executes shell commands in `/workspace`. Primary vector for running `uv init`, `uv add`, `uv run`, and applying `patch` diffs.
  * *Implementation:* Must use `asyncio.create_subprocess_exec` with `["/bin/sh", "-c", command]` (avoids direct shell invocation, more compatible with `--cap-drop=ALL`). Enforce timeout via `asyncio.wait_for`. Capture both `stdout` and `stderr`. The `cwd` must be set to `WORKSPACE_ROOT`.
  * *Return:* Combined stdout/stderr output, truncated to a sensible limit (e.g., 50KB) with a truncation notice if exceeded.
* **`lint_workspace`** `(path: str = ".")`
  * *Description:* Proactively executes `uvx ruff check <path>` and `uvx ruff format --check <path>`.
  * *Implementation:* Internally delegates to `run_bash`. The `path` argument must pass through `safe_path` validation.

### 5.2 Standard Filesystem Tools
* **`read_file`** `(filepath: str)`: Returns file contents. Must reject binary files (via `is_binary` heuristic checking for null bytes in the first 8KB) and files exceeding `MAX_READ_SIZE_BYTES` with an actionable error message.
* **`write_file`** `(filepath: str, content: str)`: Overwrites/creates a file, auto-creating missing parent directories via `os.makedirs(exist_ok=True)`. Parent directories must also pass `safe_path`. Returns confirmation with byte count written.
* **`list_directory`** `(directory_path: str = ".")`: Returns contents tagged as `[FILE]` or `[DIR]` with file sizes. Entries are sorted: directories first, then files, both alphabetically.
* **`get_file_info`** `(filepath: str)`: Returns Size (bytes), Last Modified timestamp (ISO 8601), and file permissions (octal).
* **`search_workspace`** `(pattern: str)`: Glob search (e.g., `**/*.py`), truncated to `MAX_SEARCH_RESULTS` results to protect token limits. Must exclude `.venv_container/`, `.mcp/`, `__pycache__/`, and `.git/` by default to reduce noise.

### 5.3 Advanced Editing Tools
* **`apply_patch`** `(patch_content: str)`
  * *Description:* Applies a Unified Diff (`.patch` format) to the workspace using the native `patch` utility.
  * *Implementation:* Writes the diff to a temporary file in `/tmp` (available via `tmpfs`) and executes `patch -p1 < temp.patch` via `run_bash`. The temporary file is cleaned up in a `finally` block.
  * *Validation:* Verify `patch` exit code. On failure, return the rejection message from `patch` verbatim (it includes line numbers and context).
* **`search_and_replace`** `(filepath: str, exact_search_block: str, replace_block: str)`
  * *Description:* Swaps a specific string block (highly token-efficient). Agent should be prompted to use `read_file` first to ensure perfect whitespace matching.
  * *Validation Gate:* The `exact_search_block` must exist exactly once in the file (reject if zero or multiple matches, reporting the count). Edits are performed in-memory first. Syntax validation based on file extension:
    * `.py`: `ast.parse()` — returns error type, line number, and message.
    * `.json`: `json.loads()` — returns `JSONDecodeError` details.
    * `.toml`: `tomllib.loads()` — returns parse error position.
    * Other extensions: bypass validation, write directly.
  * *Error Handling:* Rejects invalid syntax instantly, returning the specific Error Type, Line Number, and Message to the LLM to facilitate self-correction without touching the disk.

## 6. Code Quality & Project Structure
* **Strict Typing:** 100% type annotation coverage using standard Python type hints. Must pass `pyrefly` (Meta's Rust-based type checker) under strict mode.
* **Docstrings:** All modules and functions must use Google-style docstrings. Tool docstrings must be exceptionally descriptive to guide LLM behavior — these become the tool's `description` in the MCP schema.
* **Extensible Structure:** Standard modern Python package format managed by `uv`:
  ```
  agent-workspace-mcp/
  ├── src/
  │   └── agent_workspace_mcp/
  │       ├── __init__.py          # Package version & metadata
  │       ├── server.py            # FastMCP entrypoint, tool registration, logging setup
  │       ├── tools/
  │       │   ├── __init__.py      # Re-exports all tool functions
  │       │   ├── filesystem.py    # read_file, write_file, list_directory, get_file_info, search_workspace
  │       │   ├── execution.py     # run_bash, lint_workspace
  │       │   └── editing.py       # apply_patch, search_and_replace
  │       └── utils/
  │           ├── __init__.py
  │           └── security.py      # WORKSPACE_ROOT, safe_path(), env var loading
  ├── tests/
  │   ├── conftest.py              # Shared fixtures (tmp workspace, mock Context)
  │   ├── test_security.py         # Path boundary & symlink tests
  │   ├── test_filesystem.py       # Filesystem tool unit tests
  │   ├── test_execution.py        # Execution tool unit tests (mocked subprocess)
  │   ├── test_editing.py          # Editing tool unit tests (AST/JSON validation)
  │   └── test_live_workflow.py    # E2E agentic tests with litellm
  ├── pyproject.toml
  ├── .env.example                 # Template for required env vars (no secrets)
  ├── .dockerignore                # Excludes .venv, .git, tests, plans, .env
  ├── server.json                  # MCP registry manifest
  ├── Dockerfile
  └── README.md
  ```

## 7. Documentation & Client Configuration
The `README.md` must be comprehensive and include:
* **System Prompt Guidelines (Agent Workflows):** Explicit instructions for users to pass to their agents:
  * *Workflow A (Single Scripts):* Use PEP 723 inline metadata (`# /// script`) for single files and execute via `uv run`.
  * *Workflow B (Complex Projects):* Use `run_bash` for `uv init`, build multi-file structures, and manage dependencies via `uv add`.
* **Host Setup:** Instructions and JSON snippets for integrating with MCP clients (Claude Desktop, Cursor). Crucially avoids importing the host's `.env` file to prevent the LLM agent from obtaining unrestricted access to host secrets.
* **Troubleshooting:** Common issues (UID mismatch, volume mount errors, permission denied).

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
        "-v", "<HOST_TARGET_DIRECTORY>:/workspace",
        "<BUILT_IMAGE_NAME>"
      ]
    }
  }
}
```
*Note: Hardcode your host system UID:GID instead of `1000:1000` if you are on Linux and it differs from 1000. Claude Desktop will NOT evaluate bash variables directly inside the JSON array.*

## 8. Testing Strategy
* **Unit Testing:** Validate path boundary logic (`safe_path`), AST/JSON/TOML validation, binary file detection, output truncation, and input parsing using mocked filesystem operations. Use `pytest-asyncio` for async tool tests with a mock `Context`.
* **E2E Agentic Testing:** Pytest suite utilizing `litellm` and OpenRouter (via `DEFAULT_MODEL` falling back to `openrouter/google/gemini-3-flash-preview`) to test real LLM agent logic directly interacting with the running Docker container over `stdio`.
  * *Scenario 1:* Validate LLM can create a standalone Python file with PEP 723 dependencies and execute it.
  * *Scenario 2:* Validate LLM can initialize a project (`uv init`), add dependencies (`uv add`), and execute the entry point.
  * *Scenario 3:* Validate LLM can utilize `run_bash` to execute Linux tools (e.g., `grep` for string searching, `jq` for json parsing).
  * *Scenario 4:* Validate LLM can isolate syntax errors using `lint_workspace` and securely apply targeted fixes via `search_and_replace`.
  * *Scenario 5:* Validate path traversal attacks are blocked (LLM instructed to read `/etc/passwd`).

## 9. Logging & Observability Strategy
Because the server communicates over `stdio`, `stdout` corruption must be strictly prevented.
* **Protocol Safety:** Absolutely no `print()` statements. At runtime, `sys.stdout` must be redirected to `sys.stderr` to prevent any third-party library or accidental `print()` from corrupting the MCP JSON-RPC stream.
* **Native MCP Logging:** Use `FastMCP` Context (`await ctx.info()`, `await ctx.error()`, `await ctx.warning()`, `await ctx.debug()`) to stream real-time execution logs directly to the MCP client UI. Also use `await ctx.report_progress()` for long-running tools.
* **Persistent Diagnostic Logging:** Use Python's `logging` module to maintain a persistent audit trail written to `/workspace/.mcp/server.log`. A `StreamHandler` must concurrently route to `sys.stderr` (safe for `stdio` servers). Use `RotatingFileHandler` to cap log size at 5MB with 2 backups.
* **Agent-Driven Audit Logging:** System prompts should instruct the agent to use `run_bash` (`echo "step X" >> run.log`) to record its own progress during long workflows.

## 10. CI/CD & MCP Registry Publishing Constraints
* **GitHub Actions Workflow:**
  * Enforce PR linting/typing checks (`ruff`, `pyrefly`).
  * Run unit tests via `uv run pytest tests/ --ignore=tests/test_live_workflow.py`.
  * Automate Docker image build/push to GHCR on `main` commits.
  * Automate official MCP Registry publishing via the `mcp-publisher` CLI (`login github` -> `publish`).
  * Scheduled cron job (weekly) to automatically rebuild and push the Docker image to absorb upstream `uv` base image security patches.
  * E2E tests run only when `OPENROUTER_API_KEY` secret is available (not on fork PRs).

### 10.1 Required Registry Artifacts

**`.dockerignore`**
```dockerignore
.venv
.git
.github
.agents
.env
.env.example
.pytest_cache
__pycache__
tests/
plans/
*.md
!README.md
```

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

# Copy and install the server application via uv
COPY pyproject.toml /app/pyproject.toml
COPY src/ /app/src/
RUN uv pip install --system /app

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