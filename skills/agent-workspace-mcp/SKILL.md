---
name: agent-workspace-mcp
description: Provides a highly secure, containerized Linux workspace via the Model Context Protocol (MCP) mounted at /workspace. Uses this skill when the agent needs to autonomously code, test, and debug safely using filesystem, execution, and editing tools, while adhering to strict environment constraints such as mandatory use of 'uv' for Python management.
---

# Agent Workspace MCP Skill

<docs>
This skill provides access to a highly secure, containerized Linux workspace via the Model Context Protocol (MCP). The workspace is mounted at `/workspace` and serves as an "agentic playground" where you can autonomously code, test, and debug safely without risking the host machine.
</docs>

<instructions>
When you have access to this MCP server, you MUST adhere to the following rules and best practices:

## 🛡️ Environment & Security Constraints
- **Workspace Root:** All operations are confined to `/workspace`. Absolute paths MUST start with `/workspace`, and relative paths are resolved relative to it.
- **Python & Packages (`uv` is MANDATORY):** Standard `python` and `pip` commands are NOT available. You MUST use `uv` for all Python management:
  - Run scripts: `uv run script.py`
  - Install dependencies: `uv add <package>`
  - Install global CLI tools: `uv tool install <package>` (e.g., ruff, pytest)
  - Execute tools: `uvx <tool>` (e.g., `uvx ruff check .`)
  - Create new projects: `uv init`
  - Sync environments: `uv sync`
- **Timeouts & Limits:** 
  - Bash commands timeout after 60 seconds by default.
  - Bash output is truncated at 50KB. Use `head`, `tail`, or `grep` for large outputs.
  - File reads (`read_file`) are limited to 1MB. By default, it reads 100 lines. Use `offset` and `limit` to paginate.

## 🛠️ Available Tools

### Filesystem Operations
- **`list_directory(path)`**: Lists files `[F]` and directories `[D]`. Automatically excludes noise like `.git` and `.venv`.
- **`search_workspace(pattern, exclude_patterns)`**: Find files by glob (e.g., `src/**/*.py`). Note: For deep text/content search, prefer `run_bash("grep -rn ...")`.
- **`read_file(filepath, offset, limit)`**: Read file contents safely. 
- **`write_file(filepath, content)`**: Create a new file or completely overwrite an existing one. Creates missing parent directories automatically.

### Code Editing (Precision Tools)
- **`search_and_replace(filepath, edits, dry_run)`**: Your primary tool for modifying existing files.
  - Takes a list of edits: `[{"old": "exact text", "new": "replacement text"}]`.
  - **Fuzzy Whitespace Fallback:** If exact match fails, it automatically attempts to match ignoring leading/trailing whitespace and preserves relative indentation!
  - **Auto-Validation:** Automatically validates syntax for `.py`, `.json`, `.toml`, and `.yaml` files before saving to prevent corrupting the file.
  - **Best Practice:** Always read the file first (`read_file`) to ensure your `"old"` text is accurate and unique. If it fails due to multiple matches, include more surrounding lines in `"old"`.
- **`apply_patch(patch_content)`**: Apply standard Unified Diffs (`.patch` files) via `patch -p1`.

### Execution
- **`run_bash(command, timeout)`**: Execute shell commands. Supports pipes, redirects, `&&`, etc. 
  - Remember to explicitly increase the `timeout` parameter if you are running long builds, large downloads, or comprehensive test suites.

### Token-Efficient Bash Utilities
To optimize context window usage, prefer these pre-installed tools when using `run_bash`:
- **`tree`**: Generates a visual directory structure map. Extremely useful for context gathering when constrained with depth flags (e.g., `tree -L 2 -I ".venv|.git"`).
- **`fd` (fd-find)**: A fast, user-friendly alternative to `find` that automatically ignores `.git` and `.gitignore` contents.
- **`rg` (ripgrep)**: The fastest tool for searching codebase contents for specific strings or regex patterns; respects `.gitignore` by default.
- **`jq`**: Command-line JSON processor. Perfect for extracting specific fields from configuration files (like `package.json` or `server.json`) without writing custom Python scripts.
- **`curl`**: Essential for downloading external datasets, testing API endpoints, or fetching remote scripts.
- **`git`**: Core version control functionality for cloning repositories, checking out branches, and managing patches.
- **`zip` / `unzip` / `tar`**: For managing archives.
- **`procps` (`ps`, `kill`, `pkill`)**: For process management.

## 💡 Best Practices & Workflows
1. **Investigate First:** Always use `list_directory` or `search_workspace` to understand the project structure before writing code.
2. **Edit Safely:** For targeted edits, prefer `search_and_replace` over `write_file` or manual bash commands (like `sed`). It is significantly safer due to its built-in AST validation and atomic writes.
3. **Iterative Development:** Write code -> Run it (`uv run ...`) -> Check exit codes and output -> Fix errors with `search_and_replace` -> Re-run.
4. **Avoid Large Output:** If a command generates massive output, redirect it to a file (`> output.txt`) and read it iteratively, or pipe it through `grep`.
</instructions>

<example>
<thinking>
The user wants me to create a simple Python script to calculate Fibonacci numbers and run it. I need to:
1. Initialize a new uv project or just write a file.
2. Use `write_file` to create the script.
3. Execute the script using `uv run`.
4. Verify the output.
</thinking>
1. Use `write_file` to create `fibonacci.py` in `/workspace`.
2. Use `run_bash("uv run fibonacci.py")` to execute it.
3. Check the exit code and output.
</example>

<verification>
After making changes to the workspace:
- ALWAYS run `uv run <script>` or the relevant test command (e.g., `uv run pytest`) to verify your code changes.
- Ensure that the exit code is 0 and the output matches expectations.
- If there is an error, use `search_and_replace` to correct the code and re-verify.
</verification>
