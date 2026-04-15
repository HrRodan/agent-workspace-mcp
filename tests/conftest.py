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


@pytest.fixture
def agent_workspace(request) -> Path:
    """Provide a unique temporary workspace under /tmp for live agent tests.

    Returns the absolute path to the workspace. Cleans up after the test.
    """
    import uuid
    import shutil

    # Create a unique name based on the test function and a UUID
    test_name = request.node.name
    unique_id = uuid.uuid4().hex[:8]
    workspace_path = Path(f"/tmp/mcp-test-{test_name}-{unique_id}").resolve()

    workspace_path.mkdir(parents=True, exist_ok=True)

    yield workspace_path

    # Cleanup after test
    if workspace_path.exists():
        try:
            shutil.rmtree(workspace_path)
        except Exception:
            pass
