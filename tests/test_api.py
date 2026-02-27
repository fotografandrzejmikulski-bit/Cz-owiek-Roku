"""
Testy integracyjne API FastAPI (REST).
Używamy starlette.testclient.TestClient który poprawnie obsługuje lifespan.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from src.api.main import app


@pytest.fixture(scope="module")
def client():
    """Klient testowy z aktywnym lifespan (agenty uruchomione)."""
    with TestClient(app) as c:
        yield c


class TestTasksEndpoint:
    def test_submit_task_returns_accepted(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/tasks/",
            json={
                "client_id": "test_client",
                "task_type": "generate_content",
                "payload": {"theme": "test"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "task_id" in data


class TestAgentsEndpoint:
    def test_list_agents_returns_list(self, client: TestClient) -> None:
        response = client.get("/api/v1/agents/")
        assert response.status_code == 200
        agents = response.json()
        assert isinstance(agents, list)
        # Po starcie aplikacji powinno być co najmniej 3 agenty
        assert len(agents) >= 3

    def test_get_known_agent(self, client: TestClient) -> None:
        response = client.get("/api/v1/agents/content_agent")
        assert response.status_code == 200
        agent = response.json()
        assert agent["agent_id"] == "content_agent"
        assert "content" in agent["capabilities"]

    def test_get_unknown_agent_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/agents/nonexistent_agent")
        assert response.status_code == 404
