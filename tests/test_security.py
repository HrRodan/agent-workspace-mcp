import os
from pathlib import Path
import pytest
from agent_workspace_mcp.utils.security import (
    safe_path,
    is_binary,
    validate_glob_pattern,
    validate_patch_security,
)

def test_safe_path_relative(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.WORKSPACE_ROOT", tmp_path)
    
    path = safe_path("test.py")
    assert path == tmp_path / "test.py"
    assert path.is_absolute()

def test_safe_path_absolute(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.WORKSPACE_ROOT", tmp_path)
    
    absolute_target = tmp_path / "subdir" / "file.txt"
    path = safe_path(str(absolute_target))
    assert path == absolute_target

def test_safe_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.WORKSPACE_ROOT", tmp_path)
    
    with pytest.raises(ValueError, match="outside the workspace boundary"):
        safe_path("../../etc/passwd")

def test_safe_path_absolute_outside(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.WORKSPACE_ROOT", tmp_path)
    
    with pytest.raises(ValueError, match="outside the workspace boundary"):
        safe_path("/etc/passwd")

def test_safe_path_symlink_attack(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.WORKSPACE_ROOT", tmp_path)
    
    # Create a symlink pointing outside
    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("secret")
    
    link_path = tmp_path / "malicious_link"
    os.symlink(outside_file, link_path)
    
    with pytest.raises(ValueError, match="outside the workspace boundary"):
        safe_path("malicious_link")

def test_is_binary(tmp_path):
    text_file = tmp_path / "text.txt"
    text_file.write_text("Hello World")
    assert is_binary(text_file) is False
    
    binary_file = tmp_path / "binary.bin"
    binary_file.write_bytes(b"Hello\x00World")
    assert is_binary(binary_file) is True

def test_is_binary_missing_file():
    assert is_binary(Path("/non/existent/file")) is False

def test_validate_glob_pattern():
    # Valid patterns
    validate_glob_pattern("*.py")
    validate_glob_pattern("src/**/*.py")
    validate_glob_pattern("tests/test_*.py")
    
    # Invalid patterns
    with pytest.raises(ValueError, match="Invalid glob pattern"):
        validate_glob_pattern("../etc/passwd")
    with pytest.raises(ValueError, match="Invalid glob pattern"):
        validate_glob_pattern("/etc/passwd")
    with pytest.raises(ValueError, match="Invalid glob pattern"):
        validate_glob_pattern("~/roots")

def test_validate_patch_security(monkeypatch, tmp_path):
    monkeypatch.setattr("agent_workspace_mcp.utils.security.WORKSPACE_ROOT", tmp_path)
    
    # Valid patch
    valid_patch = """--- a/src/main.py
+++ b/src/main.py
@@ -1,1 +1,1 @@
-print("old")
+print("new")
"""
    validate_patch_security(valid_patch)
    
    # Valid patch with /dev/null
    new_file_patch = """--- /dev/null
+++ b/new_file.txt
@@ -0,0 +1,1 @@
+hello
"""
    validate_patch_security(new_file_patch)

    # Malicious patch 1: Traversal in header
    malicious_patch_1 = """--- a/../../../etc/passwd
+++ b/src/main.py
@@ -1,1 +1,1 @@
-old
+new
"""
    with pytest.raises(ValueError, match="Security violation in patch header"):
        validate_patch_security(malicious_patch_1)

    # Malicious patch 2: Absolute path in header
    malicious_patch_2 = """--- a/src/main.py
+++ /etc/passwd
@@ -1,1 +1,1 @@
-old
+new
"""
    with pytest.raises(ValueError, match="Security violation in patch header"):
        validate_patch_security(malicious_patch_2)
