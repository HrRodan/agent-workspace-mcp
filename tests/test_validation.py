from agent_workspace_mcp.tools.validation import validate_syntax

def test_validate_python_valid():
    content = "def foo():\n    return 42"
    assert validate_syntax(content, "test.py") is None

def test_validate_python_invalid():
    content = "def foo(:\n    return 42"
    error = validate_syntax(content, "test.py")
    assert error is not None
    assert "Python syntax error" in error

def test_validate_json_valid():
    content = '{"key": "value"}'
    assert validate_syntax(content, "test.json") is None

def test_validate_json_invalid():
    content = '{"key": "value"'
    error = validate_syntax(content, "test.json")
    assert error is not None
    assert "JSON parse error" in error

def test_validate_jsonl_valid():
    content = '{"a": 1}\n{"b": 2}\n\n{"c": 3}'
    assert validate_syntax(content, "test.jsonl") is None

def test_validate_jsonl_invalid():
    content = '{"a": 1}\n{"b": 2\n{"c": 3}'
    error = validate_syntax(content, "test.jsonl")
    assert error is not None
    assert "JSONL parse error at line 2" in error

def test_validate_toml_valid():
    content = 'key = "value"\n[section]\nfoo = 1'
    assert validate_syntax(content, "test.toml") is None

def test_validate_toml_invalid():
    content = 'key = "value\n[section]'
    error = validate_syntax(content, "test.toml")
    assert error is not None
    assert "TOML parse error" in error

def test_validate_yaml_valid():
    content = 'key: value\nlist:\n  - item1\n  - item2'
    assert validate_syntax(content, "test.yaml") is None

def test_validate_yaml_invalid():
    # Harder to make invalid YAML that isn't just a string, but tabs are forbidden in indent
    content = 'key: value\n\tinvalid: tab'
    error = validate_syntax(content, "test.yaml")
    assert error is not None
    assert "YAML parse error" in error

def test_validate_unknown_extension():
    content = "some text"
    assert validate_syntax(content, "test.txt") is None
