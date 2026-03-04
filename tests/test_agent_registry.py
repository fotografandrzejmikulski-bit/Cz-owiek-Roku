"""
Testy dla modułu AgentRegistry i DynamicRegistryAgent.

Sprawdza:
  - Ładowanie rejestru z pliku JSON
  - Poprawność wpisów (pola, typy, unikalność)
  - Metody wyszukiwania i stronicowania
  - DynamicRegistryAgent.process_task
  - Endpointy HTTP: GET /registry/agents, GET /registry/agents/{id},
                    GET /registry/agents/search, POST /registry/session
"""
from __future__ import annotations

import pytest

from src.agents.agent_registry import (
    AgentRegistry,
    AgentRegistryEntry,
    DynamicRegistryAgent,
    get_default_registry,
)
from src.communication.broker import MessageBroker
from src.communication.llm_client import MockLlmClient
from src.models.message import AgentMessage, MessageType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def broker() -> MessageBroker:
    return MessageBroker()


@pytest.fixture
def mock_llm() -> MockLlmClient:
    return MockLlmClient()


@pytest.fixture
def registry() -> AgentRegistry:
    return get_default_registry()


@pytest.fixture(scope="module")
def client(app_client):
    """Alias for session-scoped app_client from conftest."""
    return app_client


# ---------------------------------------------------------------------------
# 1. Testy rejestru (AgentRegistry)
# ---------------------------------------------------------------------------


class TestAgentRegistry:
    def test_count_equals_6666(self, registry: AgentRegistry) -> None:
        assert registry.count() == 6666

    def test_all_returns_list(self, registry: AgentRegistry) -> None:
        agents = registry.all()
        assert isinstance(agents, list)
        assert len(agents) == 6666

    def test_all_agent_ids_unique(self, registry: AgentRegistry) -> None:
        ids = [e.agent_id for e in registry.all()]
        assert len(set(ids)) == len(ids)

    def test_get_existing_agent(self, registry: AgentRegistry) -> None:
        entry = registry.get("agent_0001")
        assert entry is not None
        assert isinstance(entry, AgentRegistryEntry)
        assert entry.agent_id == "agent_0001"

    def test_get_last_agent(self, registry: AgentRegistry) -> None:
        entry = registry.get("agent_6666")
        assert entry is not None
        assert entry.agent_id == "agent_6666"

    def test_get_nonexistent_returns_none(self, registry: AgentRegistry) -> None:
        assert registry.get("agent_9999") is None
        assert registry.get("") is None
        assert registry.get("not_an_agent") is None

    def test_entry_fields_present(self, registry: AgentRegistry) -> None:
        for entry in registry.all()[:10]:
            assert entry.agent_id
            assert entry.display_name
            assert entry.domain
            assert entry.role
            assert entry.specialization
            assert entry.mission
            assert entry.category in {
                "education", "research", "creative", "scientific", "social",
                "blockchain", "alife", "wetware", "specialist", "youth",
            }
            assert entry.safety in {"safe", "monitored", "sandboxed"}
            assert entry.system_prompt

    def test_to_dict_contains_required_keys(self, registry: AgentRegistry) -> None:
        entry = registry.get("agent_0001")
        assert entry is not None
        d = entry.to_dict()
        for key in ("agent_id", "display_name", "domain", "role",
                    "specialization", "mission", "category", "safety"):
            assert key in d

    def test_search_returns_results(self, registry: AgentRegistry) -> None:
        results = registry.search("Medycyna")
        assert len(results) > 0
        assert all("Medycyna" in r.domain or "Medycyna" in r.display_name
                   or "medycyna" in r.mission.lower()
                   for r in results)

    def test_search_empty_query_returns_everything_up_to_limit(
        self, registry: AgentRegistry
    ) -> None:
        results = registry.search("", limit=50)
        assert len(results) == 50

    def test_search_no_results_for_garbage(self, registry: AgentRegistry) -> None:
        results = registry.search("xyzxyz_niemożliwe_zzz_9876")
        assert results == []

    def test_search_limit_respected(self, registry: AgentRegistry) -> None:
        results = registry.search("Agent", limit=5)
        assert len(results) <= 5

    def test_by_category(self, registry: AgentRegistry) -> None:
        entries = registry.by_category("education")
        assert len(entries) > 0
        assert all(e.category == "education" for e in entries)

    def test_by_category_unknown_returns_empty(self, registry: AgentRegistry) -> None:
        assert registry.by_category("__nonexistent__") == []

    def test_page_first(self, registry: AgentRegistry) -> None:
        page = registry.page(offset=0, limit=10)
        assert len(page) == 10
        assert page[0].agent_id == "agent_0001"

    def test_page_last(self, registry: AgentRegistry) -> None:
        page = registry.page(offset=6660, limit=100)
        assert len(page) == 6

    def test_page_out_of_range_returns_empty(self, registry: AgentRegistry) -> None:
        page = registry.page(offset=7000, limit=100)
        assert page == []

    def test_safety_distribution(self, registry: AgentRegistry) -> None:
        counts: dict[str, int] = {}
        for e in registry.all():
            counts[e.safety] = counts.get(e.safety, 0) + 1
        # safe powinno być dominujące (≥50 %)
        assert counts.get("safe", 0) >= registry.count() * 0.5

    def test_entry_from_dict_roundtrip(self, registry: AgentRegistry) -> None:
        e1 = registry.get("agent_0042")
        assert e1 is not None
        d = {
            "agent_id":       e1.agent_id,
            "display_name":   e1.display_name,
            "domain":         e1.domain,
            "role":           e1.role,
            "specialization": e1.specialization,
            "mission":        e1.mission,
            "category":       e1.category,
            "safety":         e1.safety,
            "system_prompt":  e1.system_prompt,
        }
        e2 = AgentRegistryEntry.from_dict(d)
        assert e1 == e2


# ---------------------------------------------------------------------------
# 2. Testy DynamicRegistryAgent
# ---------------------------------------------------------------------------


class TestDynamicRegistryAgent:
    @pytest.mark.asyncio
    async def test_process_task_returns_dict(
        self, broker: "MessageBroker", mock_llm: "MockLlmClient"
    ) -> None:
        registry = get_default_registry()
        entry = registry.get("agent_0100")
        assert entry is not None

        agent = DynamicRegistryAgent(entry=entry, broker=broker, llm_client=mock_llm)
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test",
            receiver_id="agent_0100",
            payload={"task": "Opisz swoją misję"},
        )
        result = await agent.process_task(msg)

        assert isinstance(result, dict)
        assert result["agent_id"] == "agent_0100"
        assert "response" in result
        assert "category" in result
        assert "safety" in result
        assert "domain" in result
        assert "role" in result
        assert "specialization" in result

    @pytest.mark.asyncio
    async def test_display_name_and_mission(
        self, broker: "MessageBroker", mock_llm: "MockLlmClient"
    ) -> None:
        registry = get_default_registry()
        entry = registry.get("agent_0200")
        assert entry is not None
        agent = DynamicRegistryAgent(entry=entry, broker=broker, llm_client=mock_llm)
        assert agent.display_name == entry.display_name
        assert agent.mission == entry.mission

    def test_get_capabilities_contains_agent_id(
        self, broker: "MessageBroker"
    ) -> None:
        registry = get_default_registry()
        entry = registry.get("agent_0300")
        assert entry is not None
        agent = DynamicRegistryAgent(entry=entry, broker=broker)
        caps = agent.get_capabilities()
        assert "agent_0300" in caps
        assert "registry_agent" in caps

    def test_get_info_returns_dict(self, broker: "MessageBroker") -> None:
        registry = get_default_registry()
        entry = registry.get("agent_0500")
        assert entry is not None
        agent = DynamicRegistryAgent(entry=entry, broker=broker)
        info = agent.get_info()
        assert info["agent_id"] == "agent_0500"
        assert "domain" in info


# ---------------------------------------------------------------------------
# 3. Testy API – registry_router
# ---------------------------------------------------------------------------


class TestRegistryAPI:
    def test_list_agents_default(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 6666
        assert data["limit"] == 100
        assert len(data["agents"]) == 100

    def test_list_agents_pagination(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents?offset=6600&limit=100")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) == 66  # 6666 - 6600

    def test_list_agents_limit_capped_at_500(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents?limit=9999")
        assert resp.status_code == 200
        assert len(resp.json()["agents"]) <= 500

    def test_get_agent_by_id_ok(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents/agent_0001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "agent_0001"

    def test_get_agent_by_id_last(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents/agent_6666")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent_6666"

    def test_get_agent_not_found(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents/agent_9999")
        assert resp.status_code == 404

    def test_search_endpoint(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents/search?q=Medycyna&limit=20")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "agents" in data

    def test_search_no_results(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents/search?q=xyzxyz_niemozliwe")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_session_ok(self, client: "TestClient") -> None:
        resp = client.post(
            "/api/v1/registry/session",
            json={"agent_id": "agent_0001", "task": "Opisz swoją specjalizację"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "agent_0001"
        assert "response" in data
        assert "domain" in data
        assert "role" in data
        assert "specialization" in data

    def test_session_agent_not_found(self, client: "TestClient") -> None:
        resp = client.post(
            "/api/v1/registry/session",
            json={"agent_id": "agent_9999", "task": "Test"},
        )
        assert resp.status_code == 404

    def test_session_empty_task_rejected(self, client: "TestClient") -> None:
        resp = client.post(
            "/api/v1/registry/session",
            json={"agent_id": "agent_0001", "task": ""},
        )
        assert resp.status_code == 422

    def test_session_for_multiple_agents(self, client: "TestClient") -> None:
        """Sprawdza że różne agenty zwracają poprawne dane."""
        for aid in ("agent_0001", "agent_1000", "agent_3333", "agent_6666"):
            resp = client.post(
                "/api/v1/registry/session",
                json={"agent_id": aid, "task": "Przedstaw się"},
            )
            assert resp.status_code == 200
            assert resp.json()["agent_id"] == aid
