import logging
import time
from agent_workspace_mcp.tools import _logging

def test_truncate():
    # Under limit
    assert _logging.truncate("abc", max_len=10) == "abc"
    # At limit
    assert _logging.truncate("abc", max_len=3) == "abc"
    # Over limit
    result = _logging.truncate("abcdef", max_len=3)
    assert result == "abc…(6 chars total)"

def test_log_tool_entry(caplog):
    logger = logging.getLogger("test_entry")
    logger.setLevel(logging.INFO)
    
    with caplog.at_level(logging.INFO):
        start = _logging.log_tool_entry(logger, "my_tool", a=1, b="very long string" * 20)
        
    assert isinstance(start, float)
    assert "TOOL_CALL my_tool" in caplog.text
    assert "a=1" in caplog.text
    assert "b='very long string" in caplog.text
    assert "chars total" in caplog.text

def test_log_tool_exit_success(caplog):
    logger = logging.getLogger("test_exit_success")
    logger.setLevel(logging.INFO)
    start = time.monotonic() - 0.1 # 100ms ago
    
    with caplog.at_level(logging.INFO):
        _logging.log_tool_exit(logger, "my_tool", start, success=True, summary="all good")
        
    assert "TOOL_DONE my_tool [OK]" in caplog.text
    assert "100ms" in caplog.text or "101ms" in caplog.text or "102ms" in caplog.text
    assert "all good" in caplog.text
    
    # NEW: Test output snippet
    with caplog.at_level(logging.INFO):
        _logging.log_tool_exit(logger, "snippet_tool", start, success=True, output="Hello " * 50)
    assert "Output snippet: 'Hello Hello " in caplog.text
    assert "total)" in caplog.text

    # Verify log level is INFO
    for record in caplog.records:
        if "TOOL_DONE" in record.message:
            assert record.levelname == "INFO"

def test_log_tool_exit_failure(caplog):
    logger = logging.getLogger("test_exit_failure")
    logger.setLevel(logging.INFO)
    start = time.monotonic()
    
    with caplog.at_level(logging.INFO):
        _logging.log_tool_exit(logger, "my_tool", start, success=False, summary="kaboom")
        
    assert "TOOL_DONE my_tool [FAIL]" in caplog.text
    assert "kaboom" in caplog.text
    
    # NEW: Test failure output snippet
    with caplog.at_level(logging.INFO):
        _logging.log_tool_exit(logger, "fail_snippet", start, success=False, output="Error detail")
    assert "Output snippet: 'Error detail'" in caplog.text

    # NEW: Test output suppression if matches summary
    caplog.clear()
    with caplog.at_level(logging.INFO):
        _logging.log_tool_exit(logger, "suppress_tool", start, success=True, summary="Duplicate", output="Duplicate")
    assert "Duplicate" in caplog.text
    assert "Output snippet" not in caplog.text

    # Verify log level is WARNING for the failure
    for record in caplog.records:
        if "fail_snippet" in record.message:
            assert record.levelname == "WARNING"
