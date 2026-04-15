import pytest
from unittest.mock import AsyncMock, patch
from agent_workspace_mcp.tools.editing import apply_patch, search_and_replace


@pytest.mark.asyncio
async def test_apply_patch_success(workspace, mock_ctx):
    test_file = workspace / "file.py"
    test_file.write_text("print('hello')\n")

    # Unified diff format
    patch_content = """--- a/file.py
+++ b/file.py
@@ -1,1 +1,1 @@
-print('hello')
+print('world')
"""

    with patch(
        "agent_workspace_mcp.tools.editing.run_bash", new_callable=AsyncMock
    ) as mock_run:
        mock_run.return_value = "[Exit code: 0]\npatching file file.py"

        result = await apply_patch(patch_content, mock_ctx)
        assert "[Exit code: 0]" in result
        assert "patching file file.py" in result
        mock_run.assert_called_once()
        # Verify it includes the patch command
        assert "patch -p1 < " in mock_run.call_args[0][0]


@pytest.mark.asyncio
async def test_search_and_replace_multi_success(workspace, mock_ctx):
    test_file = workspace / "test.py"
    test_file.write_text("def hello():\n    print('hello')\n    # comment\n")

    edits = [
        {"old": "print('hello')", "new": "print('world')"},
        {"old": "# comment", "new": "# updated"},
    ]
    result = await search_and_replace("test.py", edits, ctx=mock_ctx)

    assert "Successfully applied 2 edits" in result
    assert "print('world')" in test_file.read_text()
    assert "# updated" in test_file.read_text()
    assert "world" in result  # More robust diff check


@pytest.mark.asyncio
async def test_search_and_replace_dry_run(workspace, mock_ctx):
    test_file = workspace / "test.py"
    test_file.write_text("hello")

    edits = [{"old": "hello", "new": "world"}]
    result = await search_and_replace("test.py", edits, dry_run=True, ctx=mock_ctx)

    assert "DRY RUN" in result
    assert "-hello" in result
    assert "+world" in result
    assert test_file.read_text() == "hello"  # Not changed


@pytest.mark.asyncio
async def test_search_and_replace_syntax_error(workspace, mock_ctx):
    test_file = workspace / "test.py"
    test_file.write_text("def hello():\n    print('hello')\n")

    edits = [{"old": "print('hello')", "new": "print('world') +"}]
    result = await search_and_replace("test.py", edits, ctx=mock_ctx)

    assert "ERROR: Python syntax error" in result
    # Original file should be untouched
    assert "print('hello')" in test_file.read_text()


@pytest.mark.asyncio
async def test_search_and_replace_not_found(workspace, mock_ctx):
    test_file = workspace / "test.py"
    test_file.write_text("hello")

    result = await search_and_replace("test.py", [{"old": "missing", "new": "r"}], ctx=mock_ctx)
    assert "ERROR: Edit 0" in result
    assert "not found" in result


@pytest.mark.asyncio
async def test_search_and_replace_yaml(workspace, mock_ctx):
    test_file = workspace / "test.yaml"
    test_file.write_text("key: value\n")

    # Invalid YAML edit
    edits = [{"old": "value", "new": "value:\n  nested: invalid:"}]
    result = await search_and_replace("test.yaml", edits, ctx=mock_ctx)
    assert "ERROR: YAML parse error" in result

    # Valid YAML edit
    edits = [{"old": "value", "new": "new_value"}]
    result = await search_and_replace("test.yaml", edits, ctx=mock_ctx)
    assert "Successfully applied" in result
    assert "key: new_value" in test_file.read_text()
