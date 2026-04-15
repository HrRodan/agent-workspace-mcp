import pytest
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
    result = await run_bash("sleep 2", timeout=1, ctx=mock_ctx)
    assert "timed out after 1s" in result
    mock_ctx.error.assert_called()


@pytest.mark.asyncio
async def test_run_bash_truncation(workspace, mock_ctx):
    # Generate 60KB of output
    cmd = "python -c 'print(\"x\" * 60000)'"
    result = await run_bash(cmd, ctx=mock_ctx)
    assert "[Exit code: 0]" in result
    assert len(result) < 65000  # Including header
    assert "output truncated at 50KB" in result



