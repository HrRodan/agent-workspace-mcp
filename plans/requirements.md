# Implementation Blueprint: Sandboxed Agentic Workspace MCP Server

This document restructures the business and technical requirements into a phased implementation plan, organized logically for a developer or engineering team.

---

## Epic 1: Repository Setup & Docker Foundation
*The foundational architecture, dependency management, and container specifications.*

- [ ] **1.1 Initialize Repository Structure**
  - Create the `uv`-managed Python package structure.
  - Set up `src/mcp_agentic_workspace/`, `tests/`, and `utils/` directories.
- [ ] **1.2 Configure Dependencies (`pyproject.toml`)**
  - Define dependencies: `mcp[cli]`, `pydantic`.
  - Configure strict type checking (`mypy` or `pyright`) and linting (`ruff`).
- [ ] **1.3 Create the Dockerfile**
  - Set base image to `ghcr.io/astral-sh/uv:python3.14-trixie`.
  - Install system utilities: `curl`, `git`, `jq`, `nano`, `patch`.
  - Add OCI Label: `LABEL io.modelcontextprotocol.server.name="io.github.<yourusername>/agentic-workspace"`.
  - Set up a non-root user (`mcpuser`) and create the `/workspace` directory with appropriate permissions.
  - Set `ENTRYPOINT` to execute the Python server script.

---

## Epic 2: Core Server & Observability
*The FastMCP server initialization, async event loop, and protocol-safe logging.*

- [ ] **2.1 Initialize FastMCP**
  - Create `server.py` and instantiate the `FastMCP` application.
  - Ensure all tool definitions utilize `async def` and `asyncio` to prevent I/O blocking.
- [ ] **2.2 Implement Persistent Diagnostic Logging**
  - Configure Python's `logging` module.
  - Route standard output away from `stdout` (to prevent JSON-RPC corruption).
  - Add `StreamHandler` to route logs to `sys.stderr`.
  - Add `FileHandler` to write a persistent rotating log to `/workspace/.mcp/server.log`.
- [ ] **2.3 Implement Protocol-Native Logging**
  - Inject `FastMCP` `Context` into tool definitions to stream `ctx.info()` and `ctx.error()` directly to the client UI.

---

## Epic 3: Security Boundaries & Path Handling
*The internal guardrails to prevent breakout and enforce the workspace sandbox.*

- [ ] **3.1 Path Traversal Prevention (`utils/security.py`)**
  - Create a utility function (`resolve_safe_path(filepath)`) that resolves absolute paths and raises an exception if the target falls outside `/workspace`.
  - Apply this utility to every filesystem tool.
- [ ] **3.2 Execution Timeouts**
  - Implement a hard 30-second `asyncio.wait_for` timeout wrapper for all bash and external Python executions.

---

## Epic 4: Tool Implementation (The LLM API)
*Building the actual MCP tools with Pydantic validation and MCP annotations.*

- [ ] **4.1 Filesystem Tools (Annotated: `readOnlyHint: true`)**
  - `read_file(filepath: str)`
  - `list_directory(directory_path: str)` - Tag outputs as `[FILE]` or `[DIR]`.
  - `get_file_info(filepath: str)` - Return size and modified time.
  - `search_workspace(pattern: str)` - Glob search, truncate at 50 results.
- [ ] **4.2 Destructive Filesystem Tools (Annotated: `destructiveHint: true`)**
  - `write_file(filepath: str, content: str)` - Auto-create missing parent directories.
  - `search_and_replace(filepath: str, exact_search_block: str, replace_block: str)`
- [ ] **4.3 AST & JSON Validation Gate (For `search_and_replace`)**
  - Implement in-memory string replacement.
  - If `.py`, run `ast.parse()`. Return explicit `e.lineno` and `e.msg` if it fails.
  - If `.json`, run `json.loads()`.
  - Only write to disk if validation passes.
- [ ] **4.4 Execution Tools (Annotated: `destructiveHint: true`)**
  - `run_bash(command: str)` - Return stdout, stderr, and exit code.
- [ ] **4.5 Linting Tool (Annotated: `readOnlyHint: true`)**
  - `lint_workspace(path: str = ".")` - Execute `uvx ruff check` and `uvx ruff format --check`.

---

## Epic 5: Deployment & Client Configuration
*How the end-user safely mounts the container and configures their client.*

- [ ] **5.1 Define the Client JSON Configuration**
  - Document the exact `docker run` command required for `mcpServers` in Claude Desktop/Cursor.
- [ ] **5.2 Enforce Runtime Security Flags (In Documentation)**
  - Require `--cap-drop=ALL` and `--security-opt=no-new-privileges:true`.
  - Require Resource Quotas: e.g., `--memory="2g" --cpus="2.0"`.
- [ ] **5.3 Implement UID/GID Mapping**
  - Require the `--user $(id -u):$(id -g)` flag in the client config to ensure files written to the host mount are owned by the host user, not root.
  - Document `.env` file pass-throughs for API keys.

---

## Epic 6: Testing Strategy
*Ensuring the server works programmatically and agentically.*

- [ ] **6.1 Unit Testing (`pytest`)**
  - Mock filesystem operations.
  - Test the path traversal blocker (ensure `../../etc/passwd` fails).
  - Test the AST validation gate (ensure missing colons are caught).
- [ ] **6.2 Agentic E2E Testing**
  - Write a test using the OpenAI/Anthropic SDK wrapping the FastMCP server.
  - **Test Scenario 1 (Inline Scripts):** Prompt agent to write a single script with PEP 723 dependencies (`# /// script`) and run it via `uv run`. Assert output.
  - **Test Scenario 2 (Complex Projects):** Prompt agent to run `uv init`, `uv add`, create a multi-file architecture, and execute. Assert successful initialization.

---

## Epic 7: Documentation & Registry Publishing
*Preparing for open-source release and official MCP index inclusion.*

- [ ] **7.1 Comprehensive README**
  - Setup instructions and copy-paste JSON configurations.
  - **Agent Prompts:** Provide specific system prompt instructions teaching the agent to use PEP 723 for single scripts vs. `uv init` for applications.
  - Explain the logging strategy and where to find the `.mcp/server.log`.
- [ ] **7.2 Create `server.json` for MCP Registry**
  - Create the metadata file adhering to `https://static.modelcontextprotocol.io/schemas/2025-07-09/server.schema.json`.
- [ ] **7.3 GitHub Actions Workflow (CI/CD)**
  - Create workflow to run `ruff` and `mypy` on PRs.
  - Create publishing workflow triggering on `main` branch or releases:
    1. Build and push Docker image to GHCR.
    2. Install `mcp-publisher` CLI.
    3. Run `mcp-publisher login github` & `mcp-publisher publish` to update the registry.
  - Add a weekly cron job to automatically rebuild and push the image to absorb upstream `uv:trixie` security patches.