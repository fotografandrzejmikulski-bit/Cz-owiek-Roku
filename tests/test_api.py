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


class TestChatEndpoint:
    def test_send_chat_message_returns_accepted(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/chat/",
            json={"client_id": "desktop-1", "text": "wygeneruj treść o walce"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "chat_id" in data
        assert data["echo"] == "wygeneruj treść o walce"

    def test_chat_analytics_intent(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/chat/",
            json={"client_id": "desktop-1", "text": "analiza zachowań gracza"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"

    def test_chat_empty_text_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/chat/",
            json={"client_id": "desktop-1", "text": ""},
        )
        assert response.status_code == 422  # walidacja Pydantic

    def test_chat_missing_client_id_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/chat/",
            json={"text": "test"},
        )
        assert response.status_code == 422
