import logging
import sys
import pytest
from unittest.mock import MagicMock, patch
from agent_workspace_mcp.server import StdoutRedirector, setup_logging, mcp

def test_stdout_redirector_write_goes_to_stderr():
    real_stdout = MagicMock()
    stderr = MagicMock()
    with patch("sys.stderr", stderr):
        redirector = StdoutRedirector(real_stdout)
        redirector.write("test message")
        stderr.write.assert_called_once_with("test message")
        real_stdout.write.assert_not_called()

def test_stdout_redirector_buffer_preserves_real_stdout():
    real_stdout = MagicMock()
    real_stdout.buffer = MagicMock()
    redirector = StdoutRedirector(real_stdout)
    assert redirector.buffer == real_stdout.buffer

def test_stdout_redirector_flush_goes_to_stderr():
    real_stdout = MagicMock()
    stderr = MagicMock()
    with patch("sys.stderr", stderr):
        redirector = StdoutRedirector(real_stdout)
        redirector.flush()
        stderr.flush.assert_called_once()
        real_stdout.flush.assert_not_called()

def test_setup_logging_creates_handlers(workspace):
    # setup_logging adds handlers to the root logger
    with patch("agent_workspace_mcp.utils.security.WORKSPACE_ROOT", workspace):
        # Clear existing handlers for a clean test
        root_logger = logging.getLogger()
        root_logger.handlers = []
        
        setup_logging()
        
        # Should have at least stderr handler and rotating file handler (since workspace is writable)
        assert len(root_logger.handlers) >= 2
        
        # Verify stderr handler
        stderr_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler) and h.stream == sys.stderr]
        assert len(stderr_handlers) == 1

def test_setup_logging_readonly_workspace(workspace, monkeypatch):
    # Mock log_dir.mkdir to fail (simulate read-only)
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        mock_mkdir.side_effect = Exception("Read-only filesystem")
        
        root_logger = logging.getLogger()
        root_logger.handlers = []
        
        setup_logging()
        
        # Should only have stderr handler
        assert len(root_logger.handlers) == 1
        assert isinstance(root_logger.handlers[0], logging.StreamHandler)

@pytest.mark.asyncio
async def test_all_tools_registered():
    expected_tools = {
        "read_file", 
        "write_file", 
        "list_directory", 
        "search_workspace",
        "run_bash", 
        "search_and_replace"
    }
    registered_tools = {tool.name for tool in await mcp.list_tools()}
    assert expected_tools.issubset(registered_tools)

@pytest.mark.asyncio
async def test_tool_annotations():
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    
    # Read-only tools
    assert tools["read_file"].annotations.readOnlyHint is True
    assert tools["list_directory"].annotations.readOnlyHint is True
    assert tools["search_workspace"].annotations.readOnlyHint is True
    
    # Destructive tools
    assert tools["write_file"].annotations.destructiveHint is True
    assert tools["run_bash"].annotations.destructiveHint is True
    assert tools["search_and_replace"].annotations.destructiveHint is True
