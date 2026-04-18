import pytest
from agent_workspace_mcp.tools.filesystem import (
    read_file,
    write_file,
    list_directory,
    search_workspace,
)


@pytest.mark.asyncio
async def test_read_file(workspace, mock_ctx):
    test_file = workspace / "test.txt"
    test_file.write_text("line1\nline2\nline3\nline4")

    # Default read (first 100 lines)
    content = await read_file("test.txt", offset=0, limit=100, ctx=mock_ctx)
    assert content == "line1\nline2\nline3\nline4"

    # Limit read
    content = await read_file("test.txt", offset=0, limit=2, ctx=mock_ctx)
    assert content == "line1\nline2"

    # Offset read
    content = await read_file("test.txt", offset=2, limit=2, ctx=mock_ctx)
    assert content == "line3\nline4"


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
async def test_list_directory(workspace, mock_ctx):
    (workspace / "file.txt").write_text("file")
    (workspace / "subdir").mkdir()
    (workspace / ".git").mkdir()  # Should be excluded

    result = await list_directory(".", mock_ctx)
    assert "[F] file.txt" in result
    assert "[D] subdir" in result
    assert ".git" not in result

@pytest.mark.asyncio
async def test_list_directory_not_found(workspace, mock_ctx):
    result = await list_directory("missing", mock_ctx)
    assert "ERROR" in result





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
    (workspace / "test1.py").write_text("1")
    (workspace / "test2.py").write_text("2")

    # Use explicit exclude
    result = await search_workspace("**/*.py", exclude_patterns=["test1.py"], ctx=mock_ctx)
    assert "test2.py" in result
    assert "test1.py" not in result

    # Standard security exclude
    venv_dir = workspace / ".venv_container"
    venv_dir.mkdir()
    (venv_dir / "hidden.py").write_text("hidden")
    result = await search_workspace("**/*.py", ctx=mock_ctx)
    assert "hidden.py" not in result


@pytest.mark.asyncio
async def test_search_workspace_exact_limit(workspace, mock_ctx, monkeypatch):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.MAX_SEARCH_RESULTS", 3)
    (workspace / "1.py").write_text("1")
    (workspace / "2.py").write_text("2")
    (workspace / "3.py").write_text("3")

    result = await search_workspace("**/*.py", mock_ctx)
    assert "Found 3 matches" in result
    assert "1.py" in result
    assert "2.py" in result
    assert "3.py" in result
    assert "truncated" not in result


@pytest.mark.asyncio
async def test_search_workspace_truncated(workspace, mock_ctx, monkeypatch):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.MAX_SEARCH_RESULTS", 2)
    (workspace / "1.py").write_text("1")
    (workspace / "2.py").write_text("2")
    (workspace / "3.py").write_text("3")

    result = await search_workspace("**/*.py", mock_ctx)
    assert "Found 2 matches" in result
    assert "truncated" in result

@pytest.mark.asyncio
async def test_search_workspace_traversal_blocked(workspace, mock_ctx):
    result = await search_workspace("../../**/*.py", mock_ctx)
    assert "ERROR" in result
    assert "Path traversal or absolute paths are not allowed" in result
