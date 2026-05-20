import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def mock_docker_client():
    """Mocks the docker.from_env() call globally to avoid touching host daemon during unit tests."""
    mock_client = MagicMock()
    with patch("docker.from_env", return_value=mock_client):
        yield mock_client
