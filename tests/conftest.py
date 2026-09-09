import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.settings import Settings


@pytest.fixture()
def client(tmp_path: pytest.TempPathFactory) -> TestClient:
    settings = Settings(workspace_root=tmp_path)
    return TestClient(create_app(settings))
