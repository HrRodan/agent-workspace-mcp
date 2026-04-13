# Implementation Plan: Sandboxed Agent Workspace MCP Server

## 1. Goal Description
Build a highly secure, containerized Model Context Protocol (MCP) server providing a sandboxed environment for LLMs. The workspace will grant agents capabilities like file system manipulation, python script execution via `uv`, and shell commands through an asynchronous, `fastmcp`-powered architecture while ensuring maximum security to the host environment. The plan strictly aligns with the guidelines in `requirements.md`.

## 2. User Review Required
No breaking infrastructure changes proposed. However, please review the assumptions concerning:
> [!WARNING]
> By default, Docker maps the `-u 1000:1000` executing user. You must be certain your UID matches this if executing strictly on Linux to prevent file permission drift between host mounted volumes (`/workspace`) and the container.

## 3. System Impact
- `pyproject.toml` (Managed dependencies: `fastmcp`, `pydantic`, `uv`)
- `src/agent_workspace_mcp/` (Server and all modular tools: filesystem, execution, and editing)
- `tests/` (Both unit tests and `litellm` e2e integration)
- `Dockerfile` & `server.json` (Deployment architecture and MCP registry setup)
- `.github/workflows/ci.yml` (CI/CD definitions)

## 4. Phase 1: Environment & Dependency Scaffolding
**Objective**: Establish the foundational `uv`-managed Python project structure and configure robust dependencies.

### Step 1: Project Initialization
- **Action**: Execute `uv init .` in the root repository to generate the project scaffold (if missing). Cleanup any legacy configurations.
- **Verify**: Check `cat pyproject.toml` confirms standard project definition exists.

### Step 2: Core & Development Dependencies
- **Action**: Modify `pyproject.toml` to:
  - Add primary runtime dependencies: `fastmcp`, `pydantic`.
  - Add testing and development dependencies: `pytest`, `pytest-asyncio`, `pyrefly` (for strict typing checks), `litellm`, `python-dotenv`.
  - Expose the main entry point:
    ```toml
    [project.scripts]
    agent-workspace-mcp = "agent_workspace_mcp.server:main"
    ```
- **Verify**: Run `uv sync` to ensure the virtual environment resolves cleanly without conflicts.

## 5. Phase 2: Security & Boundary Enforcement
**Objective**: Guarantee that all execution paths and file operations are strictly localized to the `/workspace` folder.

### Step 3: Security Boundary Module
- **File**: `src/agent_workspace_mcp/utils/security.py`
- **Action**: 
  - Define `WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", "/workspace")).resolve()`. (Fallback allows local native testing outside Docker).
  - Implement `safe_path(target_path: str) -> Path`. This must resolve the target string and explicitly enforce `.is_relative_to(WORKSPACE_ROOT)`. It must inherently block directory traversal via symlinks pointing outside the root.
  - Enforce clear `ValueError` exception outputs to steer LLM behavior when bounds are breached.
- **Verify**: Run `pytest tests/test_security` to assert that executing `safe_path("../../etc/passwd")` raises a `ValueError` rather than resolving.

## 6. Phase 3: FastMCP Tool Chain Implementation
**Objective**: Outline explicit async tools. Every file manipulation heavily leverages the `security` constraints.

### Step 4: File System Utilities
- **File**: `src/agent_workspace_mcp/tools/filesystem.py`
- **Action**: Implement typed async tooling mapping via FastMCP schema auto-generation. Ensure the FastMCP `Context` is injected to stream logs directly to the MCP client:
  - `read_file(filepath: str, ctx: Context = None) -> str`: Loads files.
  - `write_file(filepath: str, content: str, ctx: Context = None) -> str`: Writes securely, orchestrating `os.makedirs(exist_ok=True)` for parent directories.
  - `list_directory(directory_path: str = ".", ctx: Context = None) -> str`: Outputs directories tagged cleanly (`[FILE]`, `[DIR]`).
  - `get_file_info(filepath: str, ctx: Context = None) -> str`: Grabs metadata (Size, Date Modified).
  - `search_workspace(pattern: str, ctx: Context = None) -> str`: Path traversal limits enforced (max 50 outputs).
- **Verify**: Run `pytest tests/test_filesystem.py` ensuring tools abort gracefully when limits or bounds fail.

### Step 5: Process Execution Tools
- **File**: `src/agent_workspace_mcp/tools/execution.py`
- **Action**: Implement task-based process tools:
  - `run_bash(command: str, ctx: Context = None) -> str`: Wrap `asyncio.create_subprocess_shell` with a strict `timeout=30` (via `asyncio.wait_for()`). Must explicitly pass `cwd=WORKSPACE_ROOT` to restrict subprocess execution context. Streams standard streams via `ctx.info()`.
  - `lint_workspace(path: str = ".", ctx: Context = None) -> str`: Automate running `uvx ruff check` and formatting limits.
- **Verify**: Execute `pytest tests/test_execution.py` focusing on timeout handling when command attempts to pause or infinite-loop.

### Step 6: Advanced Editing Tools & AST Validation
- **File**: `src/agent_workspace_mcp/tools/editing.py`
- **Action**:
  - Integrate an `apply_patch(patch_content: str, ctx: Context = None) -> str` feature:
    - Write the diff to a temporary file natively.
    - Apply using `patch -p1 < temp.patch` via `asyncio.create_subprocess_shell`.
  - Integrate a `search_and_replace(filepath: str, exact_search: str, replace: str, ctx: Context = None) -> str` feature:
    - Perform substitution in-memory exclusively.
    - Check extensions. If `.py`, execute `ast.parse()` on modified string. If `.json`, execute `json.loads()`. If other extensions, bypass validation.
    - Intercept syntax issues, outputting formatting problems and line numbers cleanly to LLM via error strings (allowing self-correction without writing to disk).
- **Verify**: Run unit tests ensuring syntactically broken replacement injections for python/json never pollute original source files, and patches apply correctly.

## 7. Phase 4: Server Aggregation & Observability
**Objective**: Connect tooling into the global standard FastMCP context.

### Step 7: FastMCP Entrypoint
- **File**: `src/agent_workspace_mcp/server.py`
- **Action**:
  - Instantiate `mcp = FastMCP("Agent Workspace MCP")`.
  - Register imported modules automatically via `@mcp.tool()`.
  - Implement custom Logging stream: Setup `os.makedirs(WORKSPACE_ROOT / ".mcp", exist_ok=True)` on startup. Route diagnostic application logging to `/workspace/.mcp/server.log`. Ban `print()`.
  - Provide `def main(): mcp.run()`.
- **Verify**: Boot server using `--help` checks, ensuring expected `stdio` interface initializes cleanly.

## 8. Phase 5: Container Deployment Strategy
**Objective**: Finalize configuration for Docker publishing.

### Step 8: Image Scaffolding
- **File**: `Dockerfile`
- **Action**: Set base to `ghcr.io/astral-sh/uv:python3.14-trixie`. Add minimal shell deps (`curl`, `git`, `jq`, `patch`, `tini`). Expose `mcpuser` identity. Use `uv pip install --system`. Wrap the python entrypoint with `tini --` to gracefully reap zombie subprocesses spawned by the agent.
- **Verify**: Validate local compilation: `docker build -t agent-workspace-mcp .`

### Step 9: MCP Registry Verification Artifacts
- **File**: `server.json`
- **Action**: Layout complete specification utilizing the new `mcp-publisher` configuration schemas pointing towards local container `args`.
- **Verify**: Ensure the manifest parses valid json format checks.

## 9. Phase 6: QA Validation & E2E
**Objective**: Guarantee that LLM systems actually work effectively using the entire suite via simulated tool loops.

### Step 10: Live Workflow Testing against Docker
- **File**: `tests/test_live_workflow.py`
- **Action**: 
  - Employ `litellm` to simulate autonomous tool-loop calls making real LLM requests. Read the deployment configuration via `os.environ.get("DEFAULT_MODEL", "openrouter/google/gemini-3-flash-preview")` and map authentication using the `OPENROUTER_API_KEY` provided in the project's `.env` file.
  - The E2E tests must validate the full architecture by orchestrating the compiled Docker container (using a `subprocess` wrapper or Docker SDK). The tests will bind `<HOST_TARGET_DIRECTORY>:/workspace`, connect to `stdio`, and interact exactly as a live MCP client would.
  - Define complete workflows such as "File Creation Tasks" and "Lint & Fix Tasks". Protect the execution in CI by enforcing `@pytest.mark.skipif("not os.environ.get('OPENROUTER_API_KEY')")`.
- **Verify**: Successfully conclude `pytest tests/test_live_workflow.py` demonstrating end-to-end task completion by the agent inside the isolated container.

### Step 11: CI/CD Binding
- **File**: `.github/workflows/ci.yml`
- **Action**: Incorporate actions processing pull-requests automatically verifying `pyrefly`, `ruff`, and overall `pytest` integrations while compiling docker images on merge. Ensure true E2E tests are isolated from public CI runners unless safe secret provisioning for OpenRouter is deployed.
- **Verify**: The Github Actions configuration is confirmed upon commit.
