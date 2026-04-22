import pytest
from fastmcp.exceptions import ToolError
from agent_workspace_mcp.tools.editing import search_and_replace


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
    with pytest.raises(ToolError) as excinfo:
        await search_and_replace("test.py", edits, ctx=mock_ctx)
    assert "Python syntax error" in str(excinfo.value)
    # Original file should be untouched
    assert "print('hello')" in test_file.read_text()


@pytest.mark.asyncio
async def test_search_and_replace_not_found(workspace, mock_ctx):
    test_file = workspace / "test.py"
    test_file.write_text("hello")
    
    with pytest.raises(ToolError) as excinfo:
        await search_and_replace("test.py", [{"old": "missing", "new": "r"}], ctx=mock_ctx)
    assert "Edit 0" in str(excinfo.value)
    assert "not found" in str(excinfo.value)


@pytest.mark.asyncio
async def test_search_and_replace_yaml(workspace, mock_ctx):
    test_file = workspace / "test.yaml"
    test_file.write_text("key: value\n")
    
    # Invalid YAML edit
    edits = [{"old": "value", "new": "value:\n  nested: invalid:"}]
    with pytest.raises(ToolError) as excinfo:
        await search_and_replace("test.yaml", edits, ctx=mock_ctx)
    assert "YAML parse error" in str(excinfo.value)

    # Valid YAML edit
    edits = [{"old": "value", "new": "new_value"}]
    result = await search_and_replace("test.yaml", edits, ctx=mock_ctx)
    assert "Successfully applied" in result
    assert "key: new_value" in test_file.read_text()


@pytest.mark.asyncio
async def test_search_and_replace_fuzzy_whitespace(workspace, mock_ctx):
    test_file = workspace / "test.py"
    # Content has specific indentation
    test_file.write_text("def func():\n    print('match me')\n")

    # Search text has wrong indentation (fuzzy match should find it)
    edits = [{"old": "  print('match me')  ", "new": "print('replaced')"}]
    result = await search_and_replace("test.py", edits, ctx=mock_ctx)

    assert "Successfully applied" in result
    assert "1 fuzzy-matched" in result
    # It should have preserved the original 4-space indent
    assert "def func():\n    print('replaced')\n" == test_file.read_text()


@pytest.mark.asyncio
async def test_search_and_replace_fuzzy_indent_preservation(workspace, mock_ctx):
    test_file = workspace / "test.py"
    test_file.write_text(
        "class MyClass:\n"
        "    def method(self):\n"
        "        pass\n"
    )

    # Search with wrong level of indent
    old_text = "  def method(self):\n    pass"
    # Replacement has relative indent (pass is indented relative to def)
    new_text = "def new_method(self):\n    return True"

    edits = [{"old": old_text, "new": new_text}]
    result = await search_and_replace("test.py", edits, ctx=mock_ctx)

    assert "Successfully applied" in result
    # The original 4-space indent of 'def method' should be preserved for 'def new_method'
    # And the +4 relative indent for 'return True' should result in 8 spaces
    expected = (
        "class MyClass:\n"
        "    def new_method(self):\n"
        "        return True\n"
    )
    assert test_file.read_text() == expected


@pytest.mark.asyncio
async def test_search_and_replace_fuzzy_ambiguous(workspace, mock_ctx):
    test_file = workspace / "test.txt"
    test_file.write_text("item\nitem\n")
    
    # 'item' matches twice fuzzily
    edits = [{"old": "  item  ", "new": "new"}]
    with pytest.raises(ToolError) as excinfo:
        await search_and_replace("test.txt", edits, ctx=mock_ctx)
    assert "Found 2 fuzzy matches" in str(excinfo.value)


@pytest.mark.asyncio
async def test_search_and_replace_crlf_normalization(workspace, mock_ctx):
    test_file = workspace / "test.txt"
    # File with CRLF
    test_file.write_bytes(b"line1\r\nline2\r\n")

    # Search with LF
    edits = [{"old": "line1\nline2", "new": "new1\nnew2"}]
    result = await search_and_replace("test.txt", edits, ctx=mock_ctx)

    assert "Successfully applied" in result
    # Note: Our implementation normalizes to LF in current_content and writes that
    assert test_file.read_text() == "new1\nnew2\n"


@pytest.mark.asyncio
async def test_search_and_replace_mixed_exact_and_fuzzy(workspace, mock_ctx):
    test_file = workspace / "test.txt" # Use .txt to bypass Python syntax validation
    test_file.write_text("exact = 1\n  fuzzy = 2\n")

    edits = [
        {"old": "exact = 1", "new": "exact = 100"},
        {"old": "  fuzzy = 2  ", "new": "fuzzy = 200"}, # mismatching edge whitespace to force fuzzy
    ]
    result = await search_and_replace("test.txt", edits, ctx=mock_ctx)

    assert "1 exact, 1 fuzzy-matched" in result
    assert "exact = 100\n  fuzzy = 200\n" == test_file.read_text()


@pytest.mark.asyncio
async def test_search_and_replace_dry_run_reports_fuzzy(workspace, mock_ctx):
    test_file = workspace / "test.txt"
    test_file.write_text("line1\n  line2\n")

    # This won't match exactly because of the indent on line2
    edits = [{"old": "line1\nline2", "new": "new1\nnew2"}]
    result = await search_and_replace("test.txt", edits, dry_run=True, ctx=mock_ctx)

    assert "DRY RUN" in result
    assert "0 exact, 1 fuzzy-matched" in result

    assert "DRY RUN" in result
    assert "0 exact, 1 fuzzy-matched" in result
    assert "+new1" in result
    assert "+new2" in result


@pytest.mark.asyncio
async def test_search_and_replace_indent_tabs(workspace, mock_ctx):
    test_file = workspace / "test.txt" # Use .txt to avoid potential ast tab issues
    test_file.write_text("def func():\n\tprint('tabs')\n")

    # Search with spaces
    edits = [{"old": "    print('tabs')", "new": "print('still tabs')"}]
    result = await search_and_replace("test.txt", edits, ctx=mock_ctx)

    assert "Successfully applied" in result
    # Should have preserved the tab
    assert "def func():\n\tprint('still tabs')\n" == test_file.read_text()


@pytest.mark.asyncio
async def test_search_and_replace_empty_old(workspace, mock_ctx):
    test_file = workspace / "test.txt"
    test_file.write_text("content")
    
    edits = [{"old": "", "new": "prefix\n"}]
    with pytest.raises(ToolError) as excinfo:
        await search_and_replace("test.txt", edits, ctx=mock_ctx)
    assert "empty 'old' text" in str(excinfo.value)
