import pytest
from fastmcp.exceptions import ToolError
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
    with pytest.raises(ToolError) as excinfo:
        await read_file("missing.txt", mock_ctx)
    assert "File 'missing.txt' not found" in str(excinfo.value)


@pytest.mark.asyncio
async def test_read_file_binary(workspace, mock_ctx):
    bin_file = workspace / "test.bin"
    bin_file.write_bytes(b"\x00\x01\x02")

    with pytest.raises(ToolError) as excinfo:
        await read_file("test.bin", mock_ctx)
    assert "appears to be binary" in str(excinfo.value)


@pytest.mark.asyncio
async def test_read_file_too_large(workspace, mock_ctx, monkeypatch):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.MAX_READ_SIZE_BYTES", 5)
    test_file = workspace / "large.txt"

    test_file.write_text("too long")

    with pytest.raises(ToolError) as excinfo:
        await read_file("large.txt", mock_ctx)
    assert "exceeds MAX_READ_SIZE_BYTES" in str(excinfo.value)


@pytest.mark.asyncio
async def test_write_file(workspace, mock_ctx):
    result = await write_file("new.txt", "content", mock_ctx)
    assert "Successfully wrote" in result
    assert (workspace / "new.txt").read_text() == "content"


@pytest.mark.asyncio
async def test_write_file_create_only_blocks_overwrite(workspace, mock_ctx):
    (workspace / "existing.txt").write_text("old")
    with pytest.raises(ToolError) as excinfo:
        await write_file("existing.txt", "new", mock_ctx)
    assert "already exists" in str(excinfo.value)
    assert (workspace / "existing.txt").read_text() == "old"


@pytest.mark.asyncio
async def test_write_file_overwrite_allowed(workspace, mock_ctx):
    (workspace / "existing.txt").write_text("old")
    result = await write_file("existing.txt", "new", create_only=False, ctx=mock_ctx)
    assert "Successfully wrote" in result
    assert (workspace / "existing.txt").read_text() == "new"


@pytest.mark.asyncio
async def test_write_file_size_guard(workspace, mock_ctx, monkeypatch):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.MAX_WRITE_SIZE_BYTES", 5)
    with pytest.raises(ToolError) as excinfo:
        await write_file("too_large.txt", "123456", mock_ctx)
    assert "exceeds MAX_WRITE_SIZE_BYTES" in str(excinfo.value)
    assert not (workspace / "too_large.txt").exists()


@pytest.mark.asyncio
async def test_write_file_validates_syntax(workspace, mock_ctx):
    # Invalid python
    with pytest.raises(ToolError) as excinfo:
        await write_file("bad.py", "def foo(:", mock_ctx)
    assert "Python syntax error" in str(excinfo.value)
    assert not (workspace / "bad.py").exists()

    # Valid python
    result = await write_file("good.py", "def foo(): pass", mock_ctx)
    assert "Successfully wrote" in result
    assert (workspace / "good.py").exists()


@pytest.mark.asyncio
async def test_write_file_validates_jsonl(workspace, mock_ctx):
    content = '{"a": 1}\n{"b": 2' # Missing bracket on line 2
    with pytest.raises(ToolError) as excinfo:
        await write_file("bad.jsonl", content, mock_ctx)
    assert "JSONL parse error at line 2" in str(excinfo.value)
    assert not (workspace / "bad.jsonl").exists()



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
    with pytest.raises(ToolError) as excinfo:
        await list_directory("missing", mock_ctx)
    assert "Path 'missing' not found" in str(excinfo.value)





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
    with pytest.raises(ToolError) as excinfo:
        await search_workspace("../../**/*.py", mock_ctx)
    assert "Path traversal or absolute paths are not allowed" in str(excinfo.value)
