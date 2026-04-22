import pytest
import logging
from fastmcp.exceptions import ToolError
from agent_workspace_mcp.tools.filesystem import read_file, write_file
from agent_workspace_mcp.tools.execution import run_bash
from agent_workspace_mcp.tools.editing import search_and_replace

@pytest.mark.asyncio
async def test_filesystem_logging(workspace, mock_ctx, caplog):
    caplog.set_level(logging.INFO)
    test_file = workspace / "log_test.txt"
    test_file.write_text("hello logging")
    
    # 1. Test read_file logging
    await read_file("log_test.txt", ctx=mock_ctx)
    assert "TOOL_DONE read_file [OK]" in caplog.text
    assert "1 lines returned" in caplog.text
    assert "Output snippet: 'hello logging'" in caplog.text
    caplog.clear()
    
    # 2. Test write_file logging
    await write_file("new_log.txt", "content", ctx=mock_ctx)
    assert "TOOL_CALL write_file(filepath='new_log.txt', content_len=7, create_only=True)" in caplog.text
    assert "TOOL_DONE write_file [OK]" in caplog.text
    # Output is same as summary, so snippet should be suppressed
    assert "Output snippet" not in caplog.text
    caplog.clear()

@pytest.mark.asyncio
async def test_execution_logging(workspace, mock_ctx, caplog):
    caplog.set_level(logging.INFO)
    
    await run_bash("echo 'hello'", ctx=mock_ctx)
    assert "TOOL_CALL run_bash(command=\"echo 'hello'\"" in caplog.text
    assert "TOOL_DONE run_bash [OK]" in caplog.text
    assert "exit_code=0" in caplog.text
    assert "Output snippet: '[Exit code: 0]\\nhello\\n'" in caplog.text
    caplog.clear()

@pytest.mark.asyncio
async def test_editing_logging(workspace, mock_ctx, caplog):
    caplog.set_level(logging.INFO)
    test_file = workspace / "edit_test.txt"
    test_file.write_text("old text")
    
    await search_and_replace(
        "edit_test.txt", 
        edits=[{"old": "old text", "new": "new text"}], 
        ctx=mock_ctx
    )
    assert "TOOL_CALL search_and_replace(filepath='edit_test.txt', edit_count=1" in caplog.text
    assert "TOOL_DONE search_and_replace [OK]" in caplog.text
    assert "1 edits (1 exact, 0 fuzzy-matched)" in caplog.text or "1 edits" in caplog.text
    assert "Output snippet:" in caplog.text
    assert "Successfully applied" in caplog.text
    caplog.clear()

@pytest.mark.asyncio
async def test_error_logging_integration(workspace, mock_ctx, caplog):
    caplog.set_level(logging.INFO)
    
    # Trigger a filesystem error (file not found)
    with pytest.raises(ToolError):
        await read_file("non_existent.txt", ctx=mock_ctx)
    
    # Entry log should still be there
    assert "TOOL_CALL read_file(filepath='non_existent.txt'" in caplog.text
    # Exit log should indicate failure and be a WARNING
    assert "TOOL_DONE read_file [FAIL]" in caplog.text
    # Output matches summary, so snippet should be suppressed
    assert "Output snippet" not in caplog.text
    assert "File 'non_existent.txt' not found" in caplog.text
    
    # Verify log level is WARNING for the failure
    found_fail = False
    for record in caplog.records:
        if "TOOL_DONE" in record.message and "[FAIL]" in record.message:
            assert record.levelname == "WARNING"
            found_fail = True
    assert found_fail
