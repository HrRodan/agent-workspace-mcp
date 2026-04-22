---
name: agent-workspace-mcp
description: Provides a highly secure, containerized Linux workspace via the Model Context Protocol (MCP) mounted at /workspace. Uses this skill when the agent needs to autonomously code, test, and debug safely using filesystem, execution, and editing tools, while adhering to strict environment constraints such as mandatory use of 'uv' for Python management.
---

# Agent Workspace MCP Skill

`\<docs\>`
This skill provides access to a highly secure, containerized Linux workspace via the Model Context Protocol (MCP). The workspace is mounted at `/workspace` and serves as an "agentic playground" where you can autonomously code, test, and debug safely without risking the host machine.
`\</docs\>`

`\<instructions\>`
When you have access to this MCP server, you MUST adhere to the following rules and best practices:

## 🛡️ Environment & Security Constraints
- **Workspace Root:** All operations are confined to `/workspace`. Absolute paths MUST start with `/workspace`, and relative paths are resolved relative to it.
- **Python & Packages (`uv` is MANDATORY):** Standard `python` and `pip` commands are NOT available. You MUST use `uv` for all Python management:
  - Run scripts: `uv run script.py`
  - Install dependencies: `uv add <package>`
  - Create new projects: `uv init`
  - Execute tools: `uvx <tool>` (e.g., `uvx ruff check .`)
- **Error Handling:** Tools raise `ToolError` on failure. If you receive an error, analyze the message and use discovery tools (`list_directory`, `read_file`) to fix your assumptions.

## 🛠️ Available Tools

### Filesystem Operations
- **`list_directory(path)`**: Lists files `[F]` and directories `[D]`. Excludes noise like `.git`, `.venv`.
- **`search_workspace(pattern, exclude_patterns)`**: Find files by glob.
- **`read_file(filepath, offset, limit)`**: Read file contents safely. 
  - **Pagination:** Default limit is 100 lines. Use `offset`/`limit` for large files.
- **`write_file(filepath, content, create_only)`**: Create a new file with **syntax validation** (Python, JSON, YAML, TOML).
  - **Overwrite Protection:** Fails if file exists unless `create_only=False`.

### Code Editing (Precision Tools)
- **`search_and_replace(filepath, edits, dry_run)`**: **PRIMARY TOOL** for modifying existing files.
  - Takes a list of edits: `[{"old": "exact text", "new": "replacement text"}]`.
  - **Fuzzy Whitespace Fallback:** If exact match fails, it ignores whitespace and preserves relative indentation!
  - **Auto-Validation:** Validates syntax before saving.
  - **Best Practice:** `read_file` first to get exact whitespace for `old` text.

### Execution
- **`run_bash(command, timeout)`**: Execute shell commands.
  - Includes: `tree`, `fd`, `rg`, `jq`, `curl`, `git`, `patch`, `zip/unzip`.
  - Defaults to 60s timeout and 50KB output truncation.

## 💡 Best Practices & Workflows
1. **Investigate First:** Always use `list_directory` or `search_workspace` to understand the project structure before writing code.
2. **Edit Safely:** For targeted edits, prefer `search_and_replace` over `write_file` or manual bash commands (like `sed`). It is significantly safer due to its built-in AST/syntax validation and atomic writes. If you must overwrite a file entirely, use `write_file` with `create_only=False`.
3. **Iterative Development:** Write code -> Run it (`uv run ...`) -> Check exit codes and output -> Fix errors with `search_and_replace` -> Re-run.
4. **Avoid Large Output:** If a command generates massive output, redirect it to a file (`> output.txt`) and read it iteratively, or pipe it through `grep`.
`\</instructions\>`

`\<example\>`
`\<thinking\>`
The user wants me to create a simple Python script to calculate Fibonacci numbers and run it. I need to:
1. Initialize a new uv project or just write a file.
2. Use `write_file` to create the script.
3. Execute the script using `uv run`.
4. Verify the output.
`\</thinking\>`
1. Use `write_file` to create `fibonacci.py` in `/workspace`.
2. Use `run_bash("uv run fibonacci.py")` to execute it.
3. Check the exit code and output.
`\</example\>`

`\<verification\>`
After making changes to the workspace:
- ALWAYS run `uv run <script>` or the relevant test command (e.g., `uv run pytest`) to verify your code changes.
- Ensure that the exit code is 0 and the output matches expectations.
- If there is an error, use `search_and_replace` to correct the code and re-verify.
`\</verification\>`
