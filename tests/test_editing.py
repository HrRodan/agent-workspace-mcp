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
    
    with patch("agent_workspace_mcp.tools.editing.run_bash", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "patching file file.py"
        
        result = await apply_patch(patch_content, mock_ctx)
        assert "patching file file.py" in result
        mock_run.assert_called_once()
        # Verify it includes the temp file path correctly
        assert "patch -p1 < /tmp/" in mock_run.call_args[0][0]

@pytest.mark.asyncio
async def test_search_and_replace_success(workspace, mock_ctx):
    test_file = workspace / "test.py"
    test_file.write_text("def hello():\n    print('hello')\n")
    
    result = await search_and_replace(
        "test.py",
        "print('hello')",
        "print('world')",
        mock_ctx
    )
    
    assert "Successfully replaced" in result
    assert "print('world')" in test_file.read_text()
    assert "print('hello')" not in test_file.read_text()

@pytest.mark.asyncio
async def test_search_and_replace_syntax_error(workspace, mock_ctx):
    test_file = workspace / "test.py"
    test_file.write_text("def hello():\n    print('hello')\n")
    
    result = await search_and_replace(
        "test.py",
        "print('hello')",
        "print('world') +", # Syntax error: trailing +
        mock_ctx
    )
    
    assert "ERROR: Python syntax error" in result
    # Original file should be untouched
    assert "print('hello')" in test_file.read_text()

@pytest.mark.asyncio
async def test_search_and_replace_not_found(workspace, mock_ctx):
    test_file = workspace / "test.py"
    test_file.write_text("hello")
    
    result = await search_and_replace(
        "test.py",
        "missing",
        "replacement",
        mock_ctx
    )
    assert "ERROR: Search block not found" in result

@pytest.mark.asyncio
async def test_search_and_replace_ambiguous(workspace, mock_ctx):
    test_file = workspace / "test.py"
    test_file.write_text("hello\nhello")
    
    result = await search_and_replace(
        "test.py",
        "hello",
        "world",
        mock_ctx
    )
    assert "ERROR: Search block found 2 times" in result

@pytest.mark.asyncio
async def test_search_and_replace_json(workspace, mock_ctx):
    test_file = workspace / "test.json"
    test_file.write_text('{"key": "value"}')
    
    result = await search_and_replace(
        "test.json",
        '"value"',
        '"new_value"',
        mock_ctx
    )
    assert "Successfully replaced" in result
    assert '"new_value"' in test_file.read_text()

@pytest.mark.asyncio
async def test_search_and_replace_json_error(workspace, mock_ctx):
    test_file = workspace / "test.json"
    test_file.write_text('{"key": "value"}')
    
    result = await search_and_replace(
        "test.json",
        '"value"',
        'value_without_quotes', # Invalid JSON
        mock_ctx
    )
    assert "ERROR: JSON parse error" in result
    assert '"value"' in test_file.read_text()
