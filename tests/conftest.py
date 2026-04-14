from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a temporary workspace and patch WORKSPACE_ROOT to point to it."""
    # We resolve it to ensure it's absolute
    resolved_tmp = tmp_path.resolve()
    monkeypatch.setattr(
        "agent_workspace_mcp.utils.security.WORKSPACE_ROOT", resolved_tmp
    )
    return resolved_tmp


@pytest.fixture
def mock_ctx() -> MagicMock:
    """Provide a mock FastMCP Context with all logging methods."""
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()
    ctx.debug = AsyncMock()
    ctx.report_progress = AsyncMock()
    return ctx
