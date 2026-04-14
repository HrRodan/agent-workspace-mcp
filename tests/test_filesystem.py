import pytest
from agent_workspace_mcp.tools.filesystem import (
    read_file, write_file, list_directory, get_file_info, search_workspace
)

@pytest.mark.asyncio
async def test_read_file(workspace, mock_ctx):
    test_file = workspace / "test.txt"
    test_file.write_text("hello world")
    
    content = await read_file("test.txt", mock_ctx)
    assert content == "hello world"
    mock_ctx.info.assert_called()

@pytest.mark.asyncio
async def test_read_file_not_found(workspace, mock_ctx):
    content = await read_file("missing.txt", mock_ctx)
    assert "ERROR: File 'missing.txt' not found" in content

@pytest.mark.asyncio
async def test_read_file_binary(workspace, mock_ctx):
    bin_file = workspace / "test.bin"
    bin_file.write_bytes(b"\x00\x01\x02")
    
    content = await read_file("test.bin", mock_ctx)
    assert "appears to be binary" in content

@pytest.mark.asyncio
async def test_read_file_too_large(workspace, mock_ctx, monkeypatch):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.MAX_READ_SIZE_BYTES", 5)
    test_file = workspace / "large.txt"

    test_file.write_text("too long")
    
    content = await read_file("large.txt", mock_ctx)
    assert "exceeds MAX_READ_SIZE_BYTES" in content

@pytest.mark.asyncio
async def test_write_file(workspace, mock_ctx):
    result = await write_file("new.txt", "content", mock_ctx)
    assert "Successfully wrote" in result
    assert (workspace / "new.txt").read_text() == "content"

@pytest.mark.asyncio
async def test_write_file_nested(workspace, mock_ctx):
    result = await write_file("subdir/new.txt", "content", mock_ctx)
    assert "Successfully wrote" in result
    assert (workspace / "subdir" / "new.txt").read_text() == "content"

@pytest.mark.asyncio
async def test_list_directory(workspace, mock_ctx):
    (workspace / "dir1").mkdir()
    (workspace / "file1.txt").write_text("1")
    (workspace / "file2.txt").write_text("2")
    
    result = await list_directory(".", mock_ctx)
    assert "[DIR]  dir1/" in result
    assert "[FILE] file1.txt (1 bytes)" in result
    assert "[FILE] file2.txt (1 bytes)" in result
    
    # Check sorting: dir first
    lines = result.split("\n")
    assert "dir1" in lines[0]

@pytest.mark.asyncio
async def test_get_file_info(workspace, mock_ctx):
    test_file = workspace / "info.txt"
    test_file.write_text("info")
    
    result = await get_file_info("info.txt", mock_ctx)
    assert "Path: info.txt" in result
    assert "Size: 4 bytes" in result
    assert "Type: file" in result

@pytest.mark.asyncio
async def test_search_workspace(workspace, mock_ctx):
    (workspace / "test1.py").write_text("print(1)")
    (workspace / "subdir").mkdir()
    (workspace / "subdir" / "test2.py").write_text("print(2)")
    (workspace / "test.txt").write_text("text")
    
    result = await search_workspace("**/*.py", mock_ctx)
    assert "test1.py" in result
    assert "subdir/test2.py" in result
    assert "test.txt" not in result

@pytest.mark.asyncio
async def test_search_workspace_exclude(workspace, mock_ctx):
    venv_dir = workspace / ".venv_container"
    venv_dir.mkdir()
    (venv_dir / "hidden.py").write_text("hidden")
    
    result = await search_workspace("**/*.py", mock_ctx)
    assert "hidden.py" not in result
