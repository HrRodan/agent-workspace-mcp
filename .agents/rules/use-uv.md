---
trigger: always_on
---

The package and project manager is uv. Run scripts with "uv run script.py" Important Commands:
| Command | Example | Action |
| :--- | :--- | :--- |
| **`uv run`** | `uv run main.py` | Run a script/command in the managed environment. |
| **`uv init`** | `uv init` | Create a new project with `pyproject.toml`. |
| **`uv add`** | `uv add pandas` | Add a dependency to the project and install it. |
| **`uv sync`** | `uv sync` | Ensure virtual env matches the lockfile exactly. |
| **`uv tool install`**| `uv tool install ruff`| Install a global CLI tool (replaces `pipx`). |
| **`uv python install`**| `uv python install 3.12`| Download and install a specific Python version. |
| **`uv lock`** | `uv lock` | Resolve dependencies and update `uv.lock`. |
| **`uv remove`** | `uv remove requests` | Remove a dependency from project and environment. |
| **`uv tree`** | `uv tree` | Display the dependency graph visually. |
| **`uv pip install`** | `uv pip install numpy` | Low-level, fast package install (classic pip style). |