# Implementation Plan: Sandboxed Agent Workspace MCP Server

## 1. Goal Description
Build a highly secure, containerized Model Context Protocol (MCP) server providing a sandboxed environment for LLMs. The workspace will grant agents capabilities like file system manipulation, Python script execution via `uv`, and shell commands through an asynchronous, `fastmcp`-powered architecture while ensuring maximum security to the host environment. This plan strictly aligns with the guidelines in `requirements.md`.

## 2. User Review Required

> [!WARNING]
> By default, Docker maps the `-u 1000:1000` executing user. You must be certain your UID matches this if executing strictly on Linux to prevent file permission drift between host mounted volumes (`/workspace`) and the container.

> [!IMPORTANT]
> The `--read-only` flag is added to the Docker runtime to prevent agent-written code from modifying container system files. This requires `/tmp` to be a `tmpfs` mount. Verify this doesn't conflict with any `uv` cache directories inside the container.

## 3. System Impact

| Component | Files Affected | Nature of Change |
|---|---|---|
| Project scaffold | `pyproject.toml` | Dependencies, entry point, tool config |
| Security module | `src/.../utils/security.py` | New file — path boundary enforcement |
| Filesystem tools | `src/.../tools/filesystem.py` | New file — 5 tools |
| Execution tools | `src/.../tools/execution.py` | New file — 2 tools |
| Editing tools | `src/.../tools/editing.py` | New file — 2 tools |
| Server entrypoint | `src/.../server.py` | New file — FastMCP instance, registration, logging |
| Package init | `src/.../__init__.py`, `tools/__init__.py`, `utils/__init__.py` | New files — re-exports |
| Test suite | `tests/` | New files — unit + E2E |
| Container | `Dockerfile`, `.dockerignore` | New files — image build |
| Registry | `server.json` | New file — MCP registry manifest |
| CI/CD | `.github/workflows/ci.yml` | New file — automated checks, build, publish |
| Documentation | `README.md` | Comprehensive setup + usage guide |

---

## 4. Phase 1: Environment & Dependency Scaffolding
**Objective**: Establish the foundational `uv`-managed Python project structure and configure robust dependencies.

### Step 1: Project Initialization
- **Action**: The project scaffold already exists (`pyproject.toml` with `uv init` output). Verify it targets Python `>=3.14` and has the correct `name`.
- **Verify**: `cat pyproject.toml` confirms `name = "agent-workspace-mcp"` and `requires-python = ">=3.14"`.

### Step 2: Core & Development Dependencies
- **Action**: Modify `pyproject.toml`:
  ```toml
  [project]
  name = "agent-workspace-mcp"
  version = "0.1.0"
  description = "A sandboxed, agentic workspace MCP server for LLMs."
  readme = "README.md"
  requires-python = ">=3.14"
  dependencies = [
      "fastmcp>=3.2.3",
      "pydantic>=2.0",
  ]

  [project.scripts]
  agent-workspace-mcp = "agent_workspace_mcp.server:main"

  [dependency-groups]
  dev = [
      "pytest>=8.0",
      "pytest-asyncio>=0.24",
      "litellm>=1.50",
      "python-dotenv>=1.0",
      "ruff>=0.9",
  ]
  ```
  Note: `pyrefly` is installed as a CLI tool via `uv tool install pyrefly`, not as a project dependency.
- **Verify**: Run `uv sync` — ensure the virtual environment resolves cleanly with zero conflicts.

### Step 3: Create Package Structure
- **Action**: Create the directory scaffolding:
  ```
  src/agent_workspace_mcp/__init__.py
  src/agent_workspace_mcp/server.py
  src/agent_workspace_mcp/tools/__init__.py
  src/agent_workspace_mcp/tools/filesystem.py
  src/agent_workspace_mcp/tools/execution.py
  src/agent_workspace_mcp/tools/editing.py
  src/agent_workspace_mcp/utils/__init__.py
  src/agent_workspace_mcp/utils/security.py
  tests/__init__.py
  tests/conftest.py
  ```
- **`__init__.py`** for the root package:
  ```python
  """Agent Workspace MCP: A sandboxed agentic workspace for LLMs."""

  __version__ = "0.1.0"
  ```
- **Verify**: `uv run python -c "import agent_workspace_mcp; print(agent_workspace_mcp.__version__)"` prints `0.1.0`.

---

## 5. Phase 2: Security & Boundary Enforcement
**Objective**: Guarantee that all execution paths and file operations are strictly localized to the `/workspace` folder.

### Step 4: Security Boundary Module
- **File**: `src/agent_workspace_mcp/utils/security.py`
- **Action**: Implement the following:

  #### 4a. Configuration Constants
  ```python
  import os
  from pathlib import Path

  WORKSPACE_ROOT: Path = Path(
      os.environ.get("WORKSPACE_ROOT", "/workspace")
  ).resolve()

  COMMAND_TIMEOUT: int = int(os.environ.get("COMMAND_TIMEOUT", "30"))
  MAX_SEARCH_RESULTS: int = int(os.environ.get("MAX_SEARCH_RESULTS", "50"))
  MAX_READ_SIZE_BYTES: int = int(os.environ.get("MAX_READ_SIZE_BYTES", str(1024 * 1024)))
  LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

  # Directories excluded from search results to reduce noise
  SEARCH_EXCLUDE_DIRS: frozenset[str] = frozenset({
      ".venv_container", ".mcp", "__pycache__", ".git", ".ruff_cache",
  })
  ```

  #### 4b. `safe_path()` Implementation
  The function must handle these cases:
  1. **Relative paths** — resolved relative to `WORKSPACE_ROOT`.
  2. **Absolute paths** — must still fall within `WORKSPACE_ROOT`.
  3. **Traversal attacks** (`../../etc/passwd`) — blocked after resolution.
  4. **Symlink attacks** — `Path.resolve()` follows symlinks; final target is checked.
  5. **Non-existent paths** — `resolve(strict=False)` handles files that don't exist yet (e.g., `write_file` to a new path).

  ```python
  def safe_path(target_path: str) -> Path:
      """Resolve a path and enforce workspace boundary.

      Args:
          target_path: Relative or absolute path string.

      Returns:
          Resolved absolute Path guaranteed to be within WORKSPACE_ROOT.

      Raises:
          ValueError: If the resolved path escapes WORKSPACE_ROOT.
      """
      candidate = Path(target_path)
      if not candidate.is_absolute():
          candidate = WORKSPACE_ROOT / candidate
      resolved = candidate.resolve(strict=False)

      if not resolved.is_relative_to(WORKSPACE_ROOT):
          raise ValueError(
              f"Path '{target_path}' resolves to '{resolved}' which is outside "
              f"the workspace boundary '{WORKSPACE_ROOT}'. "
              f"Use paths relative to /workspace."
          )
      return resolved
  ```

  #### 4c. `is_binary()` Heuristic
  ```python
  def is_binary(filepath: Path, sample_size: int = 8192) -> bool:
      """Check if a file is binary by looking for null bytes."""
      try:
          with open(filepath, "rb") as f:
              chunk = f.read(sample_size)
          return b"\x00" in chunk
      except OSError:
          return False
  ```

- **Verify**: Run `uv run pytest tests/test_security.py` — the following test scenarios must pass:
  - `safe_path("main.py")` → resolves to `WORKSPACE_ROOT / "main.py"`.
  - `safe_path("sub/dir/file.py")` → resolves relative to workspace.
  - `safe_path("../../etc/passwd")` → raises `ValueError`.
  - `safe_path("/etc/passwd")` → raises `ValueError`.
  - `safe_path("/workspace/legit.py")` → succeeds.
  - Symlink pointing outside workspace → raises `ValueError`.
  - `is_binary()` rejects compiled `.pyc` files, accepts `.py` files.

---

## 6. Phase 3: FastMCP Tool Chain Implementation
**Objective**: Implement all 9 async tools. Every file manipulation leverages the `security` module constraints. All tools use `fastmcp.Context` for MCP-native client logging.

### Step 5: Shared Test Infrastructure
- **File**: `tests/conftest.py`
- **Action**: Create shared fixtures for all tool tests:
  ```python
  import os
  import tempfile
  from pathlib import Path
  from unittest.mock import AsyncMock, MagicMock

  import pytest

  @pytest.fixture
  def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
      """Provide a temporary workspace and patch WORKSPACE_ROOT to point to it."""
      monkeypatch.setattr(
          "agent_workspace_mcp.utils.security.WORKSPACE_ROOT", tmp_path
      )
      return tmp_path

  @pytest.fixture
  def mock_ctx() -> MagicMock:
      """Provide a mock FastMCP Context with all logging methods."""
      ctx = MagicMock()
      ctx.info = AsyncMock()
      ctx.warning = AsyncMock()
      ctx.error = AsyncMock()
      ctx.debug = AsyncMock()
      ctx.report_progress = AsyncMock()
      return ctx
  ```

### Step 6: File System Utilities
- **File**: `src/agent_workspace_mcp/tools/filesystem.py`
- **Action**: Implement 5 typed async tools. Each function must:
  1. Accept `ctx: Context` as the last parameter (auto-injected by FastMCP).
  2. Call `safe_path()` on every user-supplied path.
  3. Use `await ctx.info(...)` to stream progress to the MCP client.
  4. Return `str` (FastMCP handles JSON-RPC wrapping).

  **Tool specifications:**

  #### `read_file(filepath: str, ctx: Context) -> str`
  - Resolves via `safe_path`.
  - Checks `is_binary()` — returns error string if binary.
  - Checks `file.stat().st_size > MAX_READ_SIZE_BYTES` — returns error if too large.
  - Opens with `encoding="utf-8", errors="replace"`.
  - Returns file contents as a string.

  #### `write_file(filepath: str, content: str, ctx: Context) -> str`
  - Resolves via `safe_path`.
  - Validates parent directory also passes `safe_path`.
  - Creates parent directories with `os.makedirs(exist_ok=True)`.
  - Writes atomically: write to a sibling temp file, then `os.replace()` to target.
  - Returns `"Successfully wrote {n} bytes to {filepath}"`.

  #### `list_directory(directory_path: str, ctx: Context) -> str`
  - Defaults to `"."` if not provided.
  - Resolves via `safe_path`.
  - Verifies the target is a directory.
  - Iterates with `Path.iterdir()`, sorts: dirs first, then files, alphabetically.
  - Tags each entry: `[DIR]  subdir/` or `[FILE] main.py (1234 bytes)`.
  - Returns formatted string.

  #### `get_file_info(filepath: str, ctx: Context) -> str`
  - Resolves via `safe_path`.
  - Returns formatted string:
    ```
    Path: /workspace/main.py
    Size: 1234 bytes
    Modified: 2026-04-13T12:00:00+00:00
    Permissions: 0o644
    Type: file
    ```

  #### `search_workspace(pattern: str, ctx: Context) -> str`
  - Resolves the glob relative to `WORKSPACE_ROOT`.
  - Excludes results matching any directory in `SEARCH_EXCLUDE_DIRS`.
  - Truncates at `MAX_SEARCH_RESULTS`.
  - Returns relative paths (from workspace root), one per line, with a count header.
  - If results were truncated, appends: `"... truncated at {MAX_SEARCH_RESULTS} results. Narrow your pattern."`.

- **Verify**: Run `uv run pytest tests/test_filesystem.py -v`. Test scenarios include:
  - Read a normal text file → returns content.
  - Read a binary file → returns error message.
  - Read a file larger than MAX_READ_SIZE_BYTES → returns error message.
  - Write creates parent directories.
  - Write to a path outside workspace → raises error.
  - List a directory with mixed files/dirs → sorted output.
  - List a non-existent directory → returns error.
  - Search finds `.py` files but excludes `__pycache__`.
  - Search truncates at limit.

### Step 7: Process Execution Tools
- **File**: `src/agent_workspace_mcp/tools/execution.py`
- **Action**: Implement 2 task-based process tools:

  #### `run_bash(command: str, timeout: int, ctx: Context) -> str`
  - `timeout` parameter defaults to `COMMAND_TIMEOUT` (env-configurable).
  - Creates subprocess with `asyncio.create_subprocess_exec`:
    ```python
    process = await asyncio.create_subprocess_exec(
        "/bin/sh", "-c", command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,  # merge stderr into stdout
        cwd=str(WORKSPACE_ROOT),
    )
    ```
  - Wraps `process.communicate()` with `asyncio.wait_for(timeout=timeout)`.
  - On `asyncio.TimeoutError`: kills the process (`process.kill()`), awaits it, returns error:
    `"ERROR: Command timed out after {timeout}s. The process was killed. Simplify the command or increase timeout."`
  - On normal completion: returns stdout/stderr combined.
  - **Output Truncation**: If output exceeds 50KB, truncate and append:
    `"... output truncated at 50KB. Use 'head' or 'tail' to view specific portions."`
  - Streams `await ctx.info(f"Running: {command}")` before execution and `await ctx.info(f"Exit code: {returncode}")` after.

  #### `lint_workspace(path: str, ctx: Context) -> str`
  - Validates `path` via `safe_path`.
  - Runs two commands sequentially via internal calls:
    1. `uvx ruff check {relative_path}` — returns lint diagnostics.
    2. `uvx ruff format --check {relative_path}` — returns formatting diagnostics.
  - Concatenates results with a clear separator.
  - If both pass, returns `"✓ No lint or formatting issues found."`.

- **Verify**: Run `uv run pytest tests/test_execution.py -v`. Test scenarios:
  - `run_bash("echo hello")` → returns `"hello\n"`.
  - `run_bash("sleep 60", timeout=1)` → returns timeout error, process is killed.
  - `run_bash("exit 1")` → returns non-zero exit code in output.
  - `run_bash` with long output → truncated.
  - `lint_workspace` on clean code → success message.
  - `lint_workspace` on dirty code → returns diagnostics.

### Step 8: Advanced Editing Tools & AST Validation
- **File**: `src/agent_workspace_mcp/tools/editing.py`
- **Action**:

  #### `apply_patch(patch_content: str, ctx: Context) -> str`
  - Writes `patch_content` to a temporary file (`/tmp/mcp_patch_XXXX.patch`).
  - Applies via `run_bash("patch -p1 < /tmp/mcp_patch_XXXX.patch")`.
  - Cleans up the temp file in a `finally` block.
  - Returns `patch` stdout on success.
  - On failure: returns full `patch` error output (includes context and rejected hunk details).

  #### `search_and_replace(filepath: str, exact_search_block: str, replace_block: str, ctx: Context) -> str`
  - **Step 1 — Read**: Load the file via `safe_path` + read.
  - **Step 2 — Count occurrences**: `content.count(exact_search_block)`.
    - If `0`: Return `"ERROR: Search block not found in '{filepath}'. Use read_file to verify exact content including whitespace."`.
    - If `>1`: Return `"ERROR: Search block found {n} times in '{filepath}'. Provide more context in your search block to make it unique."`.
  - **Step 3 — Replace in-memory**: `new_content = content.replace(exact_search_block, replace_block, 1)`.
  - **Step 4 — Validate syntax** (by file extension):
    - `.py`:
      ```python
      import ast
      try:
          ast.parse(new_content)
      except SyntaxError as e:
          return f"ERROR: Python syntax error at line {e.lineno}: {e.msg}. Fix and retry."
      ```
    - `.json`:
      ```python
      import json
      try:
          json.loads(new_content)
      except json.JSONDecodeError as e:
          return f"ERROR: JSON parse error at line {e.lineno}, col {e.colno}: {e.msg}. Fix and retry."
      ```
    - `.toml`:
      ```python
      import tomllib
      try:
          tomllib.loads(new_content)
      except tomllib.TOMLDecodeError as e:
          return f"ERROR: TOML parse error: {e}. Fix and retry."
      ```
    - All other extensions: skip validation.
  - **Step 5 — Write atomically**: Write to a sibling temp file, then `os.replace()`.
  - Returns `"Successfully replaced content in '{filepath}'. {len(replace_block)} chars written."`.

- **Verify**: Run `uv run pytest tests/test_editing.py -v`. Test scenarios:
  - `search_and_replace` with valid Python edit → file updated, AST validates.
  - `search_and_replace` injecting invalid Python syntax → original file preserved, error returned.
  - `search_and_replace` with non-existent search block → error returned.
  - `search_and_replace` with ambiguous (multiple) matches → error returned.
  - `search_and_replace` on `.json` file with broken JSON replacement → error returned.
  - `search_and_replace` on `.txt` file → skips validation, writes directly.
  - `apply_patch` with valid unified diff → file patched.
  - `apply_patch` with invalid/conflicting diff → error returned.

---

## 7. Phase 4: Server Aggregation & Observability
**Objective**: Connect all tooling into the FastMCP server and set up proper logging.

### Step 9: FastMCP Entrypoint
- **File**: `src/agent_workspace_mcp/server.py`
- **Action**:

  #### 9a. Server Instantiation
  ```python
  from fastmcp import FastMCP

  mcp = FastMCP(
      "Agent Workspace MCP",
      instructions=(
          "You are operating inside a sandboxed Linux workspace at /workspace. "
          "Always use read_file before search_and_replace to ensure exact whitespace matching. "
          "For new projects, use run_bash('uv init') then uv add for dependencies. "
          "For single scripts, use PEP 723 inline metadata with uv run."
      ),
  )
  ```

  #### 9b. Tool Registration
  Use FastMCP's `@mcp.tool()` decorator pattern. Import tool functions from submodules and register them explicitly:
  ```python
  from agent_workspace_mcp.tools.filesystem import (
      read_file, write_file, list_directory, get_file_info, search_workspace,
  )
  from agent_workspace_mcp.tools.execution import run_bash, lint_workspace
  from agent_workspace_mcp.tools.editing import apply_patch, search_and_replace

  # Register all tools
  mcp.add_tool(read_file)
  mcp.add_tool(write_file)
  # ... etc.
  ```

  Alternatively, if using `@mcp.tool()` directly in each submodule, the server module must import those submodules to trigger the decorator registration. **Decision: Use the standalone `@tool` decorator in submodules and import via `mcp.add_tool()` in `server.py`** — this avoids circular imports and keeps each module independently testable.

  #### 9c. Logging Setup
  ```python
  import logging
  import sys
  from logging.handlers import RotatingFileHandler
  from agent_workspace_mcp.utils.security import WORKSPACE_ROOT, LOG_LEVEL

  def setup_logging() -> None:
      """Configure dual logging: stderr + rotating file in /workspace/.mcp/."""
      log_dir = WORKSPACE_ROOT / ".mcp"
      log_dir.mkdir(parents=True, exist_ok=True)
      log_file = log_dir / "server.log"

      formatter = logging.Formatter(
          "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
          datefmt="%Y-%m-%dT%H:%M:%S",
      )

      # Stderr handler (safe for stdio servers)
      stderr_handler = logging.StreamHandler(sys.stderr)
      stderr_handler.setFormatter(formatter)

      # Rotating file handler (5MB, 2 backups)
      file_handler = RotatingFileHandler(
          log_file, maxBytes=5 * 1024 * 1024, backupCount=2,
      )
      file_handler.setFormatter(formatter)

      root_logger = logging.getLogger()
      root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
      root_logger.addHandler(stderr_handler)
      root_logger.addHandler(file_handler)
  ```

  #### 9d. Main Entrypoint
  ```python
  def main() -> None:
      """Entry point for the Agent Workspace MCP server."""
      setup_logging()
      logger = logging.getLogger(__name__)
      logger.info("Agent Workspace MCP server starting...")
      logger.info("Workspace root: %s", WORKSPACE_ROOT)
      mcp.run()  # Defaults to stdio transport

  if __name__ == "__main__":
      main()
  ```

- **Verify**:
  - `uv run python -m agent_workspace_mcp.server --help` (if FastMCP exposes CLI help) or `uv run python -c "from agent_workspace_mcp.server import mcp; print(mcp.name)"` to verify import chain.
  - Manually run `echo '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"capabilities":{},"protocolVersion":"2024-11-05","clientInfo":{"name":"test","version":"0.1.0"}}}' | uv run python -m agent_workspace_mcp.server` and verify a valid JSON-RPC response on stdout.

---

## 8. Phase 5: Container Deployment Strategy
**Objective**: Finalize Docker configuration for deployment and registry publishing.

### Step 10: `.dockerignore`
- **File**: `.dockerignore`
- **Action**: Create with the exclusions listed in requirements Section 10.1 to minimize image size and prevent leaking secrets.
- **Verify**: File exists and `.env`, `.git`, `tests/`, `plans/` are listed.

### Step 11: Dockerfile
- **File**: `Dockerfile`
- **Action**: Implement exactly as specified in requirements Section 10.1, with these specific design decisions:
  - **Base image**: `ghcr.io/astral-sh/uv:python3.14-trixie` — includes `uv` and Python 3.14 pre-installed.
  - **System deps**: `curl`, `git`, `jq`, `nano`, `patch`, `tini` — minimal set for agent workflows.
  - **Install strategy**: `uv pip install --system /app` — installs the project and its dependencies system-wide. The `pyproject.toml` is copied first (before `src/`) to leverage Docker layer caching for dependency resolution.
  - **User**: `mcpuser` (UID 1000) is created and set before the `ENTRYPOINT`.
  - **ENTRYPOINT**: `tini -- python -m agent_workspace_mcp.server` — `tini` handles signal forwarding and zombie reaping as PID 1.
- **Verify**: Local image build succeeds:
  ```bash
  docker build -t agent-workspace-mcp .
  ```
  Quick smoke test:
  ```bash
  echo '{}' | docker run -i --rm agent-workspace-mcp
  # Should output a JSON-RPC error (invalid request) — proves the server starts
  ```

### Step 12: MCP Registry Manifest
- **File**: `server.json`
- **Action**: Create as specified in requirements Section 10.1. Follows the `mcp-publisher` schema.
- **Verify**: `python -m json.tool server.json` parses without error.

---

## 9. Phase 6: QA Validation & E2E

### Step 13: Unit Test Suite
- **Files**: `tests/test_security.py`, `tests/test_filesystem.py`, `tests/test_execution.py`, `tests/test_editing.py`
- **Action**: Implement comprehensive unit tests as described in each phase's "Verify" section above.
- **Key testing patterns**:
  - Use `workspace` fixture (from `conftest.py`) to redirect `WORKSPACE_ROOT` to `tmp_path`.
  - Use `mock_ctx` fixture for FastMCP Context.
  - Use `pytest.mark.asyncio` for all async tool tests.
  - Mock `asyncio.create_subprocess_exec` in execution tests to avoid actual shell calls.
  - For filesystem tests, create real files in `tmp_path`.
- **Verify**: `uv run pytest tests/ --ignore=tests/test_live_workflow.py -v` — all pass.

### Step 14: E2E Agentic Testing
- **File**: `tests/test_live_workflow.py`
- **Action**:
  - Employ `litellm` to simulate autonomous tool-loop calls making real LLM requests.
  - Read the deployment configuration via `os.environ.get("DEFAULT_MODEL", "openrouter/google/gemini-3-flash-preview")`.
  - Authenticate using the `OPENROUTER_API_KEY` from the project's `.env`.
  - The E2E tests must orchestrate the compiled Docker container:
    1. Build the image (or use a pre-built tag).
    2. Start the container with `docker run -i --rm` and all security flags.
    3. Connect to stdin/stdout using `asyncio.create_subprocess_exec`.
    4. Send MCP `initialize` handshake.
    5. Drive the LLM tool-calling loop.
    6. Assert expected outcomes (file creation, execution output, lint results).
  - Guard with: `@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="No API key")`.
  - **Scenarios**:
    1. **PEP 723 Script**: Agent creates a Python file with inline metadata and runs it.
    2. **Project Bootstrap**: Agent inits a project, adds deps, runs entry point.
    3. **Linux Tools**: Agent uses `grep`, `jq`, `curl` via `run_bash`.
    4. **Lint & Fix**: Agent lints, detects errors, fixes via `search_and_replace`.
    5. **Security Boundary**: Agent attempts to read `/etc/passwd` — must fail gracefully.
- **Verify**: `uv run pytest tests/test_live_workflow.py -v` with `OPENROUTER_API_KEY` set.

### Step 15: CI/CD Pipeline
- **File**: `.github/workflows/ci.yml`
- **Action**: Create a GitHub Actions workflow with the following jobs:
  ```yaml
  name: CI
  on:
    push:
      branches: [main]
    pull_request:
      branches: [main]
    schedule:
      - cron: "0 6 * * 1"  # Weekly Monday 06:00 UTC

  jobs:
    lint-and-type-check:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v4
        - run: uv sync
        - run: uv run ruff check src/
        - run: uv run ruff format --check src/
        - run: uvx pyrefly check src/

    unit-tests:
      runs-on: ubuntu-latest
      needs: lint-and-type-check
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v4
        - run: uv sync
        - run: uv run pytest tests/ --ignore=tests/test_live_workflow.py -v

    docker-build:
      runs-on: ubuntu-latest
      needs: unit-tests
      steps:
        - uses: actions/checkout@v4
        - run: docker build -t agent-workspace-mcp .
        # Smoke test: server starts and responds to initialize
        - run: |
            echo '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"capabilities":{},"protocolVersion":"2024-11-05","clientInfo":{"name":"ci","version":"0.1.0"}}}' \
            | timeout 10 docker run -i --rm agent-workspace-mcp \
            | head -1 | python -m json.tool

    docker-publish:
      if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'
      runs-on: ubuntu-latest
      needs: docker-build
      permissions:
        packages: write
      steps:
        - uses: actions/checkout@v4
        - uses: docker/login-action@v3
          with:
            registry: ghcr.io
            username: ${{ github.actor }}
            password: ${{ secrets.GITHUB_TOKEN }}
        - run: |
            docker build -t ghcr.io/hrrodan/agent-workspace-mcp:latest \
                          -t ghcr.io/hrrodan/agent-workspace-mcp:${{ github.sha }} .
            docker push ghcr.io/hrrodan/agent-workspace-mcp --all-tags

    e2e-tests:
      if: github.event_name != 'pull_request'
      runs-on: ubuntu-latest
      needs: docker-build
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v4
        - run: uv sync
        - run: docker build -t agent-workspace-mcp .
        - run: uv run pytest tests/test_live_workflow.py -v
          env:
            OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
            DEFAULT_MODEL: openrouter/google/gemini-3-flash-preview
  ```
- **Verify**: Commit and push — Actions tab shows green status.

---

## 10. Phase 7: Documentation & Polish

### Step 16: README.md
- **Action**: Write a comprehensive README covering:
  1. **Project overview** — what the server does, architecture diagram (mermaid).
  2. **Quick Start** — building the image, configuring Claude Desktop/Cursor.
  3. **Tool Reference** — all 9 tools with descriptions and example usage.
  4. **Agent Workflow Guidelines** — Workflow A (PEP 723) and Workflow B (project structure).
  5. **Configuration** — environment variable table from requirements Section 3.
  6. **Security Model** — what's sandboxed and why.
  7. **Development** — contributing guidelines, running tests, CI/CD.
  8. **Troubleshooting** — common issues (UID mismatch, volume permissions, timeout tuning).
- **Verify**: README renders correctly on GitHub (push and check).

### Step 17: `.env.example`
- **File**: `.env.example`
- **Action**: Create a template:
  ```env
  # Required for E2E tests
  OPENROUTER_API_KEY=sk-or-v1-your-key-here
  DEFAULT_MODEL=openrouter/google/gemini-3-flash-preview

  # Optional server configuration overrides
  # COMMAND_TIMEOUT=30
  # MAX_SEARCH_RESULTS=50
  # MAX_READ_SIZE_BYTES=1048576
  # LOG_LEVEL=INFO
  ```
- **Verify**: File exists and `.env` is in `.gitignore`.

---

## 11. Open Questions

> [!IMPORTANT]
> **Q1: Docker Layer Caching for `uv pip install --system`.**
> The current Dockerfile copies `pyproject.toml` then `src/` as separate layers. Does `uv pip install --system /app` perform an editable install or a full install? If editable, source changes won't invalidate the dependency layer. If full, every source change rebuilds deps. We should verify the behavior and potentially split into `uv pip install --system -r requirements.txt` (deps only) + `COPY src/` (source only) for optimal caching.

> [!NOTE]
> **Q2: `--read-only` Filesystem Interaction with `uv` — RESOLVED (Option A).**
> When the agent runs `uv init` or `uv add` inside the container, `uv` writes to `~/.cache/uv`. With `--read-only`, this would fail. **Decision:** Mount an ephemeral `tmpfs` at `/home/mcpuser/.cache` (`--tmpfs /home/mcpuser/.cache:size=512m`). This gives `uv` a writable cache during the session (improving install speed for repeated `uv add` calls) while remaining fully ephemeral — the cache is discarded when the container exits (`--rm`). The Docker args in the requirements and Dockerfile have been updated accordingly.

> [!IMPORTANT]
> **Q3: `search_and_replace` Uniqueness Enforcement.**
> The current design requires the search block to appear exactly once. If the agent needs to replace multiple identical lines (e.g., repeated import statements), it must use `apply_patch` instead. Should we add an optional `occurrence: int` parameter, or is the strict uniqueness constraint the right design for LLM safety?

---

## 12. Verification Plan

### Automated Tests
| Test Type | Command | Gate |
|---|---|---|
| Lint | `uv run ruff check src/ && uv run ruff format --check src/` | CI (all PRs) |
| Type check | `uvx pyrefly check src/` | CI (all PRs) |
| Unit tests | `uv run pytest tests/ --ignore=tests/test_live_workflow.py -v` | CI (all PRs) |
| Docker build | `docker build -t agent-workspace-mcp .` | CI (all PRs) |
| Docker smoke | MCP `initialize` handshake via stdin → valid JSON-RPC response | CI (all PRs) |
| E2E agentic | `uv run pytest tests/test_live_workflow.py -v` | CI (main only, secret required) |

### Manual Verification
1. **Claude Desktop Integration**: Configure `server.json` snippet in Claude Desktop, connect, and run a multi-step coding task.
2. **Cursor Integration**: Test the same with Cursor's MCP settings.
3. **Permission Test (Linux)**: Run with `--user $(id -u):$(id -g)` and verify files created in `/workspace` are owned by the host user.
4. **Resource Exhaustion**: Have the agent run `stress --cpu 4 --timeout 60` and verify Docker `--cpus` and `--memory` caps prevent host degradation.
