# Detailed Implementation Plan: Sandboxed Agentic Workspace MCP Server

This document serves as the comprehensive architectural and step-by-step implementation blueprint for the Sandboxed Agentic Workspace MCP Server.

## 1. System Architecture & Boundaries

The architecture securely connects an LLM agent instance to an isolated Python sandboxed environment inside a Docker container.

### 1.1 Container Specification
* **Base Image**: `ghcr.io/astral-sh/uv:python3.14-trixie`
* **Package Management**: Managed by `uv` for minimal footprint and deterministic dependency resolution. The environment will explicitly run with `UV_PROJECT_ENVIRONMENT=/opt/venv` forcing virtual environment installation outside the mapped host `/workspace` folder to avoid MacOS/Linux binary collisions.
* **Network & IPC Boundaries**: Driven entirely by standard input/output (`stdio`) via JSON-RPC. Container ephemeral nature (`--rm` flag) prevents persistent state corruption.
* **Host Capabilities**: `--memory="2g" --cpus="2.0" --cap-drop=ALL --security-opt=no-new-privileges:true`.

### 1.2 Tech Core & Dependencies
* **Server Framework**: `fastmcp` (3.x by jlowin). Chosen for decorator-based routing `(@mcp.tool())` and explicit asynchronous support.
* **Input Validation**: `pydantic`. Input typing and schemas seamlessly convert to JSON schema capabilities in FastMCP.
* **Static Analysis**: `pyrefly`, installed and initialized for strict type checking. Command flow: `uv run pyrefly init` followed by `uv run pyrefly check`.
* **Testing & Sandbox Validation**:
  * Functional testing: `pytest`, `pytest-asyncio`.
  * Live LLM validation: `openai-agents` interacting as a host proxy.

---

## 2. Directory Structure

```text
agent-workspace-mcp/
├── Dockerfile
├── pyproject.toml
├── README.md
├── src/
│   └── agent_workspace_mcp/
│       ├── __init__.py
│       ├── server.py
│       ├── utils/
│       │   ├── __init__.py
│       │   └── security.py      # Path resolution and jail constraints
│       └── tools/
│           ├── __init__.py
│           ├── execution.py     # Shell interaction / subprocess
│           ├── filesystem.py    # Reads, writes, list directories
│           └── editing.py       # Syntax-validated editing
└── tests/
    ├── __init__.py
    ├── test_security.py
    ├── test_filesystem.py
    ├── test_execution.py
    └── test_live_agent.py
```

---

## 3. Module & Component Specifications

### 3.1 `src/agent_workspace_mcp/utils/security.py`
**Purpose**: Enforce the host container mapping boundary (`/workspace`).
**Functions**:
* `def resolve_target_path(filepath: str) -> Path:`
  * Normalizes the path using `pathlib.Path(filepath).resolve()`.
  * Verifies that the resulting absolute path resides completely under `Path("/workspace")`.
  * **Failure mode**: Raises a `ValueError` or custom `SecurityBoundaryError` describing the traversal block (`../` or unauthorized roots) explicitly.

### 3.2 `src/agent_workspace_mcp/tools/execution.py`
**Dependencies**: `asyncio`, `subprocess`.
* **`run_bash(command: str) -> str`**:
  * Spawns: `process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd="/workspace")`.
  * Wraps in `await asyncio.wait_for(process.communicate(), timeout=120)`.
  * **Returns**: Captured STDOUT and STDERR, or explicitly formatted Timeout message. Evaluates `process.returncode` and outputs it cleanly.
* **`lint_workspace(path: str = ".") -> str`**:
  * Maps internally to `run_bash("ruff check {path} && ruff format --check {path}")`. Ensure command executes inside `/workspace` or `.venv` dynamically.

### 3.3 `src/agent_workspace_mcp/tools/filesystem.py`
**Dependencies**: `os`, `pathlib`, `shutil`.
* **`read_file(filepath: str) -> str`**:
  * Calls `resolve_target_path(filepath)`, reads text, handles UTF-8 decoding.
* **`write_file(filepath: str, content: str) -> str`**:
  * Calls `resolve_target_path`.
  * `target.parent.mkdir(parents=True, exist_ok=True)`. Writes content payload natively.
* **`list_directory(directory_path: str = ".") -> str`**:
  * Reads nodes, affixes `[DIR]` or `[FILE]` to each line so the LLM intuitively understands tree hierarchy without extra round trips.
* **`get_file_info(filepath: str) -> dict`**:
  * Extracts sizes `os.stat().st_size` and formatted `datetime.fromtimestamp(os.stat().st_mtime)`.
* **`search_workspace(pattern: str) -> str`**:
  * Syntactic sugar executing `ripgrep` globally in `/workspace` mapped via `run_bash("rg '{pattern}' | head -n 50")`.

### 3.4 `src/agent_workspace_mcp/tools/editing.py`
**Dependencies**: `ast`, `json`.
* **`search_and_replace(filepath: str, exact_search_block: str, replace_block: str) -> str`**:
  * Reads the whole file. Fails if `exact_search_block` is not found or matched identically.
  * Replaces strictly in memory: `new_content = old_content.replace(exact_search_block, replace_block)`.
  * Security/Syntax gate: 
    * If filepath ends in `.py`: `ast.parse(new_content)`.
    * If filepath ends in `.json`: `json.loads(new_content)`.
  * **Failure mode**: Evaluates the inner `SyntaxError` exception from `ast.parse`, capturing `e.msg` and `e.lineno`, and returns an explicit instruction: `SyntaxError at line {lineno}: {msg}. Edit reversed safely, please adjust formatting constraint and try again.`
  * Writes to disk ONLY if syntax parsing yields no exceptions.

### 3.5 `src/agent_workspace_mcp/server.py`
**Dependencies**: `fastmcp`.
* Instantiate: `mcp = FastMCP("AgenticWorkspace")`.
* Use native FastAPI-like decorators `@mcp.tool()` attached to the functions defined in the `tools/` directory.
* Map explicit annotations for the API to process: `destructiveHint: true` (executors/writes) and `readOnlyHint: true` (list/read/search).
* Expose the core standard input interface: `mcp.run()`.

---

## 4. Live E2E Testing Protocol

### 4.1 `tests/test_live_agent.py`
This component proves real-world LLM feasibility.
**Dependencies**: `openai-agents` SDK.
* **Setup Phase**:
  1. Initialize `Agent` with `name="Python Sandbox Manager"` and explicit instructions (`"You are evaluating computational access. Compute the 15th Fibonacci number using a python script via your available tools."`).
  2. Map standard models (e.g. `gpt-4o` or openrouter equivalent) using LiteLLM/OpenAI standard proxy.
  3. Load the local `mcp.run()` capability or mock it logically using standard `AgentOutputSchema`.
* **Execution Phase**:
  1. Trigger `Runner.run_sync()`.
  2. Programmatic assertions to monitor tool dispatch output.
* **Verification Phase**:
  1. The LLM must emit an intent to `write_file(filepath="fib.py", ...)` followed by `run_bash(command="python fib.py")`.
  2. Subprocess stdout must yield integer `610`. The py test fails strictly if an unexpected failure limits agent loop operations.  

---

## 5. Execution Steps

* **Step 1: Environments & Types**  
  Initialize `pyproject.toml`, establish `fastmcp` and `openai-agents`. Configure the exact `ghcr.io/astral-sh/uv:python3.14-trixie` Dockerfile ensuring correct variables (`UV_PROJECT_ENVIRONMENT`).  
  *Verify: `uv check` and `uv run pyrefly init` creates base typings successfully.*

* **Step 2: Utility & Filesystem Tools**  
  Implement strict jail resolution logic in `security.py`. Flesh out functions in `filesystem.py`.  
  *Verify: Path traversal tests raise explicit `SecurityBoundaryError`. Tests for directory read operations simulate local data successfully.*

* **Step 3: Stateful Execution & Edits**  
  Develop `run_bash` tracking timeout buffers limit to 120 seconds. Implement `editing.py` AST/JSON gatekeepers.  
  *Verify: `test_execution.py` confirms `run_bash("sleep 130")` gracefully exits out. Incorrect AST string replacements fail and do not mutate filesystem test nodes.*

* **Step 4: FastMCP Composition**  
  Merge all sub-components into `server.py`. Start exposing tools to fastmcp decorators.  
  *Verify: Validate exported JSON capabilities JSON dump using `mcp.get_tools()` assertions.*

* **Step 5: Live Testing Validation**  
  Script the `openai-agents` interaction logic. Connect the underlying simulated standard tools as active elements available to the Agent loop.  
  *Verify: LLM execution completes organically generating correct output files and returning `610` locally.*
