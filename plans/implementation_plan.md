# Implementation Plan: Sandboxed Agent Workspace MCP Server

This implementation plan acts as the definitive roadmap for configuring the Agent Workspace MCP, structured entirely around the provided `requirements.md` Product Requirements Document.

## Phase 1: Environment & Dependency Initialization

**Step 1: Project Scaffolding**
- *Action*: Run `uv init` in the repository root to guarantee standard layout creation if not already present.
- *Action*: Guarantee the deletion of legacy configuration if `pyproject.toml` is malformed.
- *Verification*: `ls -l` reveals `pyproject.toml`.

**Step 2: Core Dependencies Configuration**
- *Action*: Configure `pyproject.toml`.
  - Main dependencies: `fastmcp`, `pydantic`.
  - Dev/Test dependencies: `pyrefly`, `pytest`, `pytest-asyncio`, `litellm`, `python-dotenv`.
- *Action*: Define the executable entry point.
  ```toml
  [project.scripts]
  agent-workspace-mcp = "agent_workspace_mcp.server:main"
  ```
- *Verification*: `uv sync` resolves the tree successfully without conflicts.

## Phase 2: Security & Utility Foundations

**Step 3: Security Boundary Module**
- *File*: `src/agent_workspace_mcp/utils/security.py`
- *Implementation*:
  - Define `WORKSPACE_ROOT = Path("/workspace").resolve()` or fallback to a relative local path.
  - Implement `safe_path(target_path: str) -> Path`. This function must ensure the resolved target path `is_relative_to(WORKSPACE_ROOT)`.
  - Throw a clear `ValueError` explicitly informing the LLM the path must be constrained to the workspace if traversal constraints fail.
- *Verification*: Pytest suite running `safe_path("../../passwords")` properly asserting rejection.

## Phase 3: FastMCP Tool Chains

**Step 4: Execution & Environment Tools**
- *File*: `src/agent_workspace_mcp/tools/execution.py`
- *Implementation*:
  - Implement `async def run_bash(command: str) -> str`.
    - Wrapper utilizing `asyncio.create_subprocess_shell`.
    - Integrate `asyncio.wait_for(..., timeout=30)` to enforce PRD timeout limits.
  - Implement `async def lint_workspace(path: str = ".") -> str`.
    - Fires `uvx ruff check` and `uvx ruff format --check` to proactively enforce quality via shell.

**Step 5: File System Utilities**
- *File*: `src/agent_workspace_mcp/tools/filesystem.py`
- *Implementation*:
  - Implement `read_file(filepath: str) -> str`.
  - Implement `write_file(filepath: str, content: str) -> str` (with `os.makedirs(exist_ok=True)` logic for parents).
  - Implement `list_directory(directory_path: str) -> str` formatting out `[DIR]` and `[FILE]` cleanly.
  - Implement `get_file_info(filepath: str) -> str`.
  - Implement `search_workspace(pattern: str) -> str` wrapping `pathlib.Path.rglob()` constrained strictly to 50 results.
  - *Constraint*: Every tool here must invoke `security.safe_path(filepath)` first.

**Step 6: Advanced Editing Safety**
- *File*: `src/agent_workspace_mcp/tools/editing.py`
- *Implementation*:
  - Implement `search_and_replace(filepath: str, exact_search_block: str, replace_block: str) -> str`.
  - Replace functionality executed entirely in-memory first.
  - `ast.parse(modified_memory_string)` verification if the file matches `*.py`.
  - Catch `SyntaxError`, returning `line`, `offset`, and descriptive text avoiding a destructive write.
  - If valid, execute `write_file`.

## Phase 4: Core Server Aggregation

**Step 7: The FastMCP Entrypoint**
- *File*: `src/agent_workspace_mcp/server.py`
- *Implementation*:
  - Instantiation: `mcp = FastMCP("Agent Workspace MCP")`.
  - Import all tools from the `tools/` directory modules.
  - Register tools via `@mcp.tool()` mapping them to the server context.
  - Handle persistent logging: Add logging configuration binding `logging.StreamHandler(sys.stderr)` and optionally dropping a log into `/workspace/.mcp/server.log`.
  - Define `def main(): mcp.run()`.

## Phase 5: Container deployment

**Step 8: Dockerization**
- *File*: `Dockerfile`
- *Implementation*:
  - Adopt `FROM ghcr.io/astral-sh/uv:python3.14-trixie`.
  - Include apt installs `curl`, `git`, `jq`, `nano`, `patch`.
  - Execute Unix configuration defining UID 1000 (`mcpuser`).
  - Configure `ENV UV_PROJECT_ENVIRONMENT=/workspace/.venv_container` to ensure host-volume compatibility.
  - `uv pip install --system fastmcp pydantic`.
  - Set specific `ENTRYPOINT ["python", "-m", "agent_workspace_mcp.server"]`.

**Step 9: MCP Registry Verification Artifacts**
- *File*: `server.json`
- *Implementation*: Drop the JSON structure strictly formatted around the new `mcp-publisher` configuration for registry submission.

## Phase 6: QA Validation & E2E

**Step 10: Live Workflow Testing**
- *File*: `tests/test_live_workflow.py`
- *Implementation*:
  - Hook into `litellm` importing the specific `getenv("DEFAULT_MODEL", "openrouter/google/gemini-3-flash-preview")`.
  - Run **File Creation Task**: Instruct model to "create a file called Hello.py" and verify file execution.
  - Run **Search Task**: Instruct model to "search for the string 'ERROR' inside log.txt using `grep`". Verify `run_bash` formats stdout cleanly.
  - Run **Linting & Fixing Task**: Initialize a file with syntax errors, instruct model to "use `lint_workspace` to find errors, then use `search_and_replace` to fix them". Verify fixed file state.
  - Guarantee context extraction confirms tools execute cleanly via simulated FastMCP STDIO execution hooks.

**Step 11: CI/CD Binding**
- *File*: `.github/workflows/ci.yml`
- *Implementation*: Add a basic workflow to ensure `uvx ruff check`, `uv run pyrefly check`, and `uv run pytest` pass cleanly on Pull Requests.
