"""Syntax validation utilities for the Agent Workspace MCP."""

import ast
import json
import logging
from pathlib import Path

import tomllib

logger = logging.getLogger(__name__)


def validate_syntax(content: str, filepath: str) -> str | None:
    """Validate syntax for known file types.

    Returns None on success, or an error message string on failure.
    """
    ext = Path(filepath).suffix.lower()

    if ext == ".py":
        try:
            ast.parse(content)
        except SyntaxError as e:
            return f"Python syntax error at line {e.lineno}: {e.msg}"
        except Exception as e:
            return f"Python parsing error: {str(e)}"

    elif ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return f"JSON parse error at line {e.lineno}: {e.msg}"

    elif ext == ".jsonl":
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                return f"JSONL parse error at line {i}: {e.msg}"

    elif ext == ".toml":
        try:
            tomllib.loads(content)
        except Exception as e:
            return f"TOML parse error: {str(e)}"

    elif ext in (".yaml", ".yml"):
        try:
            import yaml
            yaml.safe_load(content)
        except ImportError:
            logger.warning("yaml module not found, skipping YAML validation")
        except Exception as e:
            return f"YAML parse error: {str(e)}"

    return None
