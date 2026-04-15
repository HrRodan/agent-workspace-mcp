import pytest
from agent_workspace_mcp.tools.filesystem import (
    read_file,
    list_directory,
    search_workspace,
)
from agent_workspace_mcp.tools.editing import search_and_replace


@pytest.mark.asyncio
async def test_live_tool_workflow(workspace, mock_ctx):
    """Verifies all improved tools in a sequential workspace workflow."""

    # 1. Setup workspace structure
    (workspace / "src").mkdir()
    (workspace / "docs").mkdir()

    main_py = workspace / "src" / "main.py"
    main_py.write_text(
        "import os\n\ndef run():\n    print('Hello')\n\nif __name__ == '__main__':\n    run()\n"
    )

    readme_md = workspace / "README.md"
    readme_md.write_text("# Project\n\nLicense: MIT\n\nAuthor: Paul\n")

    # 2. Test list_directory (New Tool)
    dir_list = await list_directory(".", mock_ctx)
    assert "[D] src" in dir_list
    assert "[D] docs" in dir_list
    assert "[F] README.md" in dir_list

    # 3. Test read_file with limit (Improved Tool)
    # Read first 3 lines of main.py
    partial_read = await read_file("src/main.py", limit=3, ctx=mock_ctx)
    assert "import os" in partial_read
    assert "def run():" in partial_read
    assert "print('Hello')" not in partial_read

    # 4. Test search_workspace with exclude (Improved Tool)
    # Search for all py files but exclude src/main.py (should be empty)
    search_res = await search_workspace(
        "**/*.py", exclude_patterns=["src/main.py"], ctx=mock_ctx
    )
    assert "No files found" in search_res

    # Search for all py files (should find main.py)
    search_res = await search_workspace("**/*.py", ctx=mock_ctx)
    assert "src/main.py" in search_res

    # 5. Test search_and_replace multi-edit (Overhauled Tool)
    edits = [
        {"old": "print('Hello')", "new": "print('Hello World')"},
        {"old": "    run()", "new": "    run() # called"},
    ]
    edit_res = await search_and_replace("src/main.py", edits, ctx=mock_ctx)

    assert "Successfully applied 2 edits" in edit_res
    assert "Hello World" in edit_res  # Diff output check
    assert "called" in edit_res  # Diff output check

    # Verify file content
    updated_content = main_py.read_text()
    assert "print('Hello World')" in updated_content
    assert "run() # called" in updated_content

    # 6. Test YAML validation (New Capability)
    config_yml = workspace / "config.yaml"
    config_yml.write_text("app: agent\n")

    # Invalid YAML edit
    bad_edit = [{"old": "agent", "new": "agent:\n  broken: :"}]
    yml_res = await search_and_replace("config.yaml", bad_edit, ctx=mock_ctx)
    assert "ERROR: YAML parse error" in yml_res
    assert config_yml.read_text() == "app: agent\n"  # Verify no write on error
