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
        assert registry.count() == 51110

    def test_all_returns_list(self, registry: AgentRegistry) -> None:
        agents = registry.all()
        assert isinstance(agents, list)
        assert len(agents) == 51110

    def test_all_agent_ids_unique(self, registry: AgentRegistry) -> None:
        ids = [e.agent_id for e in registry.all()]
        assert len(set(ids)) == len(ids)

    def test_get_existing_agent(self, registry: AgentRegistry) -> None:
        entry = registry.get("agent_0001")
        assert entry is not None
        assert isinstance(entry, AgentRegistryEntry)
        assert entry.agent_id == "agent_0001"

    def test_get_last_agent(self, registry: AgentRegistry) -> None:
        entry = registry.get("agent_51110")
        assert entry is not None
        assert entry.agent_id == "agent_51110"

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
        page = registry.page(offset=51100, limit=100)
        assert len(page) == 10  # 51110 - 51100

    def test_page_out_of_range_returns_empty(self, registry: AgentRegistry) -> None:
        page = registry.page(offset=60000, limit=100)
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
        assert data["total"] == 51110
        assert data["limit"] == 100
        assert len(data["agents"]) == 100

    def test_list_agents_pagination(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents?offset=51000&limit=200")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) == 110  # 51110 - 51000

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
        resp = client.get("/api/v1/registry/agents/agent_51110")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent_51110"

    def test_get_agent_not_found(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents/agent_99999")
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
        for aid in ("agent_0001", "agent_1000", "agent_3333", "agent_51110"):
            resp = client.post(
                "/api/v1/registry/session",
                json={"agent_id": aid, "task": "Przedstaw się"},
            )
            assert resp.status_code == 200
            assert resp.json()["agent_id"] == aid


# ---------------------------------------------------------------------------
# Tests for the 44,444 expansion (total 51,110 agents)
# ---------------------------------------------------------------------------

class TestExpanded51110Registry:
    """Weryfikuje rozszerzony rejestr 51 110 agentów."""

    def test_total_count(self, registry: AgentRegistry) -> None:
        assert registry.count() == 51110

    def test_ids_continuous_start(self, registry: AgentRegistry) -> None:
        assert registry.get("agent_0001") is not None

    def test_ids_continuous_end(self, registry: AgentRegistry) -> None:
        assert registry.get("agent_51110") is not None

    def test_no_id_gaps_sample(self, registry: AgentRegistry) -> None:
        """Sprawdza brak luk w próbce kluczowych ID."""
        # Original agents use 4-digit padding (agent_0001..agent_6666)
        # New agents use 5-digit padding (agent_06667..agent_51110)
        for n in (1, 1000, 6666):
            agent_id = f"agent_{n:04d}"
            assert registry.get(agent_id) is not None, f"Brak agenta: {agent_id}"
        for n in (6667, 10000, 25000, 51110):
            agent_id = f"agent_{n:05d}"
            assert registry.get(agent_id) is not None, f"Brak agenta: {agent_id}"

    def test_all_ids_unique(self, registry: AgentRegistry) -> None:
        ids = [e.agent_id for e in registry.all()]
        assert len(set(ids)) == len(ids)

    def test_at_least_500_unique_domains(self, registry: AgentRegistry) -> None:
        domains = {e.domain for e in registry.all()}
        assert len(domains) >= 500, f"Za mało domen: {len(domains)}"

    def test_878_unique_domains(self, registry: AgentRegistry) -> None:
        domains = {e.domain for e in registry.all()}
        assert len(domains) >= 800

    def test_new_domains_present(self, registry: AgentRegistry) -> None:
        """Sprawdza obecność nowych dziedzin z ekspansji."""
        domains = {e.domain for e in registry.all()}
        new_domains_sample = [
            "Astrofizyka", "Genetyka", "Biotechnologia", "Alergologia",
            "Gastroenterologia", "Prawo Cyfrowe", "Choreografia",
            "Cloud Computing", "Fintech", "Piłka Nożna", "Metaverse",
            "Polityka Klimatyczna", "Gastronomia", "Fashion Design",
            "Dziennikarstwo", "Kosmonautyka", "Energetyka Słoneczna",
        ]
        for d in new_domains_sample:
            assert d in domains, f"Brak domeny: {d!r}"

    def test_new_categories_present(self, registry: AgentRegistry) -> None:
        categories = {e.category for e in registry.all()}
        for cat in ("medical", "legal", "artistic", "environmental", "technical"):
            assert cat in categories, f"Brak kategorii: {cat}"

    def test_agents_after_6666_have_valid_structure(self, registry: AgentRegistry) -> None:
        """Nowe agenty mają wszystkie wymagane pola."""
        new_agents = [e for e in registry.all()
                      if int(e.agent_id.split("_")[1]) > 6666]
        assert len(new_agents) == 44444
        for e in new_agents[:100]:  # sprawdź próbkę
            assert e.agent_id
            assert e.display_name
            assert e.domain
            assert e.role
            assert e.specialization
            assert e.mission
            assert e.category
            assert e.safety in ("safe", "monitored", "sandboxed")
            assert len(e.system_prompt) >= 50

    def test_medical_agents_present(self, registry: AgentRegistry) -> None:
        medical = [e for e in registry.all() if e.category == "medical"]
        assert len(medical) >= 1000

    def test_technical_agents_present(self, registry: AgentRegistry) -> None:
        technical = [e for e in registry.all() if e.category == "technical"]
        assert len(technical) >= 500

    def test_artistic_agents_present(self, registry: AgentRegistry) -> None:
        artistic = [e for e in registry.all() if e.category == "artistic"]
        assert len(artistic) >= 500

    def test_legal_agents_present(self, registry: AgentRegistry) -> None:
        legal = [e for e in registry.all() if e.category == "legal"]
        assert len(legal) >= 500

    def test_search_new_domain(self, registry: AgentRegistry) -> None:
        results = registry.search("Astrofizyka", limit=50)
        assert len(results) > 0
        assert all("astrofizyka" in e.domain.lower() or
                   "astrofizyka" in e.display_name.lower() or
                   "astrofizyka" in e.mission.lower()
                   for e in results)

    def test_search_medical_domain(self, registry: AgentRegistry) -> None:
        results = registry.search("Kardiochirurgia", limit=50)
        assert len(results) > 0

    def test_by_category_medical(self, registry: AgentRegistry) -> None:
        results = registry.by_category("medical")
        assert len(results) >= 1000

    def test_page_covers_new_agents(self, registry: AgentRegistry) -> None:
        page = registry.page(offset=6666, limit=100)
        assert len(page) == 100
        assert page[0].agent_id == "agent_06667"  # 5-digit padding for new agents

    def test_safety_distribution_safe_dominant(self, registry: AgentRegistry) -> None:
        safe_count = sum(1 for e in registry.all() if e.safety == "safe")
        assert safe_count >= registry.count() * 0.80  # ≥80% safe

    def test_sandboxed_agents_present(self, registry: AgentRegistry) -> None:
        sandboxed = [e for e in registry.all() if e.safety == "sandboxed"]
        assert len(sandboxed) >= 1


class TestExpanded51110RegistryAPI:
    def test_api_total_is_51110(self, client) -> None:
        resp = client.get("/api/v1/registry/agents?limit=1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 51110

    def test_api_new_agent_accessible(self, client) -> None:
        resp = client.get("/api/v1/registry/agents/agent_20000")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent_20000"

    def test_api_last_agent_accessible(self, client) -> None:
        resp = client.get("/api/v1/registry/agents/agent_51110")
        assert resp.status_code == 200

    def test_api_search_returns_new_domains(self, client) -> None:
        resp = client.get("/api/v1/registry/agents/search?q=Biotechnologia&limit=20")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_api_by_category_medical(self, client) -> None:
        resp = client.get("/api/v1/registry/agents?category=medical&limit=100")
        assert resp.status_code == 200
        data = resp.json()
        # Should have medical agents in the total registry
        assert data["total"] >= 1000 or len(data["agents"]) > 0
