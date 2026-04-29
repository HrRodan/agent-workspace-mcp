import pytest
from unittest.mock import patch
from fastmcp.exceptions import ToolError
from agent_workspace_mcp.tools.execution import run_bash


@pytest.mark.asyncio
async def test_run_bash_success(workspace, mock_ctx):
    # This might actually run a shell command if not mocked,
    # but since we are in a sandboxed test environment it's mostly fine.
    # We'll test with a simple echo.
    result = await run_bash("echo 'test'", ctx=mock_ctx)
    assert "[Exit code: 0]" in result
    assert "test" in result
    mock_ctx.info.assert_called()


@pytest.mark.asyncio
async def test_run_bash_failure(workspace, mock_ctx):
    # Test failure case
    result = await run_bash("exit 1", ctx=mock_ctx)
    assert "[Exit code: 1]" in result
    mock_ctx.info.assert_called()


@pytest.mark.asyncio
async def test_run_bash_timeout(workspace, mock_ctx):
    # Test timeout with sleep
    with pytest.raises(ToolError) as excinfo:
        await run_bash("sleep 2", timeout=1, ctx=mock_ctx)
    assert "timed out after 1s" in str(excinfo.value)
    mock_ctx.error.assert_called()


@pytest.mark.asyncio
async def test_run_bash_truncation(workspace, mock_ctx):
    # Generate 60KB of output
    cmd = "python -c 'print(\"x\" * 60000)'"
    result = await run_bash(cmd, ctx=mock_ctx)
    assert "[Exit code: 0]" in result
    assert len(result) < 65000  # Including header
    assert "output truncated at 50KB" in result

@pytest.mark.asyncio
async def test_run_bash_stderr_merged(workspace, mock_ctx):
    # Redirect stderr to stdout manually in the command to verify it's captured
    result = await run_bash("ls /non_existent_dir", ctx=mock_ctx)
    assert "[Exit code: 2]" in result
    assert "No such file or directory" in result

@pytest.mark.asyncio
async def test_run_bash_general_exception(workspace, mock_ctx, monkeypatch):
    # Force an exception in asyncio.create_subprocess_exec
    async def mock_subprocess(*args, **kwargs):
        raise RuntimeError("Subprocess failure")
    
    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
        with pytest.raises(ToolError) as excinfo:
            await run_bash("ls", ctx=mock_ctx)
        assert "Subprocess failure" in str(excinfo.value)
