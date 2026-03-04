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
        assert registry.count() == 55555

    def test_all_returns_list(self, registry: AgentRegistry) -> None:
        agents = registry.all()
        assert isinstance(agents, list)
        assert len(agents) == 55555

    def test_all_agent_ids_unique(self, registry: AgentRegistry) -> None:
        ids = [e.agent_id for e in registry.all()]
        assert len(set(ids)) == len(ids)

    def test_get_existing_agent(self, registry: AgentRegistry) -> None:
        entry = registry.get("agent_0001")
        assert entry is not None
        assert isinstance(entry, AgentRegistryEntry)
        assert entry.agent_id == "agent_0001"

    def test_get_last_agent(self, registry: AgentRegistry) -> None:
        entry = registry.get("agent_55555")
        assert entry is not None
        assert entry.agent_id == "agent_55555"

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
        page = registry.page(offset=55500, limit=100)
        assert len(page) == 55  # 55555 - 55500

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
        assert data["total"] == 55555
        assert data["limit"] == 100
        assert len(data["agents"]) == 100

    def test_list_agents_pagination(self, client: "TestClient") -> None:
        resp = client.get("/api/v1/registry/agents?offset=55400&limit=200")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) == 155  # 55555 - 55400

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
        resp = client.get("/api/v1/registry/agents/agent_55555")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent_55555"

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
        for aid in ("agent_0001", "agent_1000", "agent_3333", "agent_55555"):
            resp = client.post(
                "/api/v1/registry/session",
                json={"agent_id": aid, "task": "Przedstaw się"},
            )
            assert resp.status_code == 200
            assert resp.json()["agent_id"] == aid


# ---------------------------------------------------------------------------
# Tests for the 44,444 expansion (total 51,110 agents)
# ---------------------------------------------------------------------------

class TestExpanded51110Registry:  # formerly 51110, now 55555
    """Weryfikuje rozszerzony rejestr 55 555 agentów."""

    def test_total_count(self, registry: AgentRegistry) -> None:
        assert registry.count() == 55555

    def test_ids_continuous_start(self, registry: AgentRegistry) -> None:
        assert registry.get("agent_0001") is not None

    def test_ids_continuous_end(self, registry: AgentRegistry) -> None:
        assert registry.get("agent_55555") is not None

    def test_no_id_gaps_sample(self, registry: AgentRegistry) -> None:
        """Sprawdza brak luk w próbce kluczowych ID."""
        # Original agents use 4-digit padding (agent_0001..agent_6666)
        # New agents use 5-digit padding (agent_06667..agent_51110)
        for n in (1, 1000, 6666):
            agent_id = f"agent_{n:04d}"
            assert registry.get(agent_id) is not None, f"Brak agenta: {agent_id}"
        for n in (6667, 10000, 25000, 51110, 55555):
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
        assert len(new_agents) == 48889  # 44444 + 4445
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


class TestExpanded51110RegistryAPI:  # updated to 55555
    def test_api_total_is_55555(self, client) -> None:
        resp = client.get("/api/v1/registry/agents?limit=1")
        assert resp.status_code == 200
        assert resp.json()["total"] == 55555

    def test_api_new_agent_accessible(self, client) -> None:
        resp = client.get("/api/v1/registry/agents/agent_20000")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent_20000"

    def test_api_last_agent_accessible(self, client) -> None:
        resp = client.get("/api/v1/registry/agents/agent_55555")
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


# ---------------------------------------------------------------------------
# Tests for the 4,445 Coding / Game / Creative agent expansion (total 55,555)
# ---------------------------------------------------------------------------

class TestCodingGameExpansion55555:
    """Weryfikuje 4 445 wyspecjalizowanych agentów: coding, gry, komiksy, książki."""

    def test_total_count_55555(self, registry: AgentRegistry) -> None:
        assert registry.count() == 55555

    def test_last_agent_id_55555(self, registry: AgentRegistry) -> None:
        entry = registry.get("agent_55555")
        assert entry is not None
        assert entry.agent_id == "agent_55555"

    def test_coding_expansion_count(self, registry: AgentRegistry) -> None:
        """Nowych agentów (po 51110) powinno być dokładnie 4445."""
        new_agents = [e for e in registry.all()
                      if int(e.agent_id.split("_")[1]) > 51110]
        assert len(new_agents) == 4445

    def test_aaagame_domains_present(self, registry: AgentRegistry) -> None:
        domains = {e.domain for e in registry.all()}
        aaa_domains = [
            "Silnik Unreal Engine", "Silnik Unity", "Silnik Godot",
            "Programowanie Gier AAA", "Gameplay Programming",
            "AI Przeciwników w Grach", "Level Design AAA",
        ]
        for d in aaa_domains:
            assert d in domains, f"Brak domeny AAA: {d!r}"

    def test_indie_game_domains_present(self, registry: AgentRegistry) -> None:
        domains = {e.domain for e in registry.all()}
        indie_domains = [
            "Indie Game Development", "Pixel Art Games", "2D Game Programming",
            "Platformer Design", "Roguelike Design", "Visual Novel Development",
            "Pygame Development", "GameMaker Studio",
        ]
        for d in indie_domains:
            assert d in domains, f"Brak domeny indie: {d!r}"

    def test_mobile_platform_domains_present(self, registry: AgentRegistry) -> None:
        domains = {e.domain for e in registry.all()}
        mobile_domains = [
            "iOS Development Swift", "Android Development Kotlin",
            "Cross-Platform React Native", "Cross-Platform Flutter",
            "Jetpack Compose", "SwiftUI Development",
        ]
        for d in mobile_domains:
            assert d in domains, f"Brak domeny mobile: {d!r}"

    def test_console_platform_domains_present(self, registry: AgentRegistry) -> None:
        domains = {e.domain for e in registry.all()}
        console_domains = [
            "PlayStation 5 Development", "Xbox Series X Development",
            "Nintendo Switch Development", "Steam Deck Development",
            "VR Game Development Oculus", "AR Game Development iOS",
        ]
        for d in console_domains:
            assert d in domains, f"Brak domeny konsoli: {d!r}"

    def test_comics_domains_present(self, registry: AgentRegistry) -> None:
        domains = {e.domain for e in registry.all()}
        comics_domains = [
            "Pisanie Komiksów", "Rysowanie Komiksów", "Lettering Komiksów",
            "Manga Tworzenie", "Webtoon Creation", "Kolorowanie Komiksów",
        ]
        for d in comics_domains:
            assert d in domains, f"Brak domeny komiksów: {d!r}"

    def test_books_ebooks_domains_present(self, registry: AgentRegistry) -> None:
        domains = {e.domain for e in registry.all()}
        book_domains = [
            "Pisanie Powieści", "Pisanie Science Fiction", "Pisanie Fantasy",
            "Ebook Production", "Kindle Direct Publishing",
            "Technical Writing Books", "Ghost Writing",
        ]
        for d in book_domains:
            assert d in domains, f"Brak domeny książki: {d!r}"

    def test_programming_language_domains_present(self, registry: AgentRegistry) -> None:
        domains = {e.domain for e in registry.all()}
        prog_domains = [
            "Python Programming", "C++ Programming", "Rust Programming",
            "Go Programming", "Java Programming", "C# Programming",
            "TypeScript Programming", "Kotlin Programming",
        ]
        for d in prog_domains:
            assert d in domains, f"Brak domeny programowania: {d!r}"

    def test_new_agents_have_code_system_prompt(self, registry: AgentRegistry) -> None:
        """Nowe agenty coding/game mają rozbudowane system_prompt."""
        new_agents = [e for e in registry.all()
                      if int(e.agent_id.split("_")[1]) > 51110]
        sample = new_agents[:50]
        for e in sample:
            assert "najlepszym ekspertem" in e.system_prompt or "specjalizującym" in e.system_prompt
            assert len(e.system_prompt) >= 80

    def test_creative_category_in_new_agents(self, registry: AgentRegistry) -> None:
        new_agents = [e for e in registry.all()
                      if int(e.agent_id.split("_")[1]) > 51110]
        categories = {e.category for e in new_agents}
        assert "creative" in categories or "artistic" in categories

    def test_search_unreal_engine(self, registry: AgentRegistry) -> None:
        results = registry.search("Unreal", limit=20)
        assert len(results) > 0

    def test_search_python_programming(self, registry: AgentRegistry) -> None:
        results = registry.search("Python Programming", limit=20)
        assert len(results) > 0

    def test_search_comics(self, registry: AgentRegistry) -> None:
        results = registry.search("Komiks", limit=20)
        assert len(results) > 0

    def test_search_fantasy_writing(self, registry: AgentRegistry) -> None:
        results = registry.search("Fantasy", limit=20)
        assert len(results) > 0


# ---------------------------------------------------------------------------
# Tests for: unique names, domain browsing, and chat/task endpoints
# ---------------------------------------------------------------------------

class TestUniqueDisplayNames:
    """Każdy z 55,555 agentów musi mieć unikalną nazwę display_name."""

    def test_all_display_names_unique(self, registry: AgentRegistry) -> None:
        names = [e.display_name for e in registry.all()]
        assert len(set(names)) == len(names), (
            f"Znaleziono duplikaty: {len(names) - len(set(names))} powtórzeń"
        )

    def test_display_names_not_empty(self, registry: AgentRegistry) -> None:
        for e in registry.all():
            assert e.display_name, f"{e.agent_id} ma pustą nazwę"

    def test_first_few_agents_have_unique_names(self, registry: AgentRegistry) -> None:
        first_100 = registry.page(offset=0, limit=100)
        names = [e.display_name for e in first_100]
        assert len(set(names)) == len(names)


class TestDomainMethods:
    """Testy metod AgentRegistry.by_domain() i .domains()."""

    def test_domains_returns_dict(self, registry: AgentRegistry) -> None:
        d = registry.domains()
        assert isinstance(d, dict)
        assert len(d) >= 1000, f"Za mało domen: {len(d)}"

    def test_domains_total_equals_count(self, registry: AgentRegistry) -> None:
        d = registry.domains()
        total = sum(d.values())
        assert total == registry.count()

    def test_domains_sorted_alphabetically(self, registry: AgentRegistry) -> None:
        keys = list(registry.domains().keys())
        assert keys == sorted(keys)

    def test_by_domain_python(self, registry: AgentRegistry) -> None:
        agents = registry.by_domain("Python Programming")
        assert len(agents) >= 1
        for a in agents:
            assert a.domain == "Python Programming"

    def test_by_domain_unreal(self, registry: AgentRegistry) -> None:
        agents = registry.by_domain("Silnik Unreal Engine")
        assert len(agents) >= 1

    def test_by_domain_unknown_returns_empty(self, registry: AgentRegistry) -> None:
        agents = registry.by_domain("Nieistniejąca Dziedzina XYZ99")
        assert agents == []

    def test_by_domain_count_matches_domains_dict(self, registry: AgentRegistry) -> None:
        d = registry.domains()
        sample_domain = next(iter(d))
        assert len(registry.by_domain(sample_domain)) == d[sample_domain]


class TestDomainBrowseAPI:
    """Testy endpointów GET /api/v1/registry/domains."""

    def test_list_domains_status_200(self, client) -> None:
        resp = client.get("/api/v1/registry/domains?limit=10")
        assert resp.status_code == 200

    def test_list_domains_total_correct(self, client) -> None:
        resp = client.get("/api/v1/registry/domains?limit=1")
        data = resp.json()
        assert data["total_domains"] >= 1000
        assert data["total_agents"] == 55555

    def test_list_domains_pagination(self, client) -> None:
        resp = client.get("/api/v1/registry/domains?offset=0&limit=5")
        data = resp.json()
        assert len(data["domains"]) == 5
        assert data["offset"] == 0
        assert data["limit"] == 5

    def test_list_domains_each_has_count(self, client) -> None:
        resp = client.get("/api/v1/registry/domains?limit=20")
        for item in resp.json()["domains"]:
            assert "domain" in item
            assert "agent_count" in item
            assert item["agent_count"] >= 1

    def test_list_domains_by_offset(self, client) -> None:
        r1 = client.get("/api/v1/registry/domains?offset=0&limit=3").json()["domains"]
        r2 = client.get("/api/v1/registry/domains?offset=3&limit=3").json()["domains"]
        names1 = [d["domain"] for d in r1]
        names2 = [d["domain"] for d in r2]
        assert set(names1).isdisjoint(set(names2))

    def test_get_agents_in_domain_python(self, client) -> None:
        resp = client.get("/api/v1/registry/domains/Python%20Programming")
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "Python Programming"
        assert data["total"] >= 1
        assert len(data["agents"]) >= 1

    def test_get_agents_in_domain_pagination(self, client) -> None:
        resp = client.get(
            "/api/v1/registry/domains/Python%20Programming?offset=0&limit=3"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) <= 3

    def test_get_agents_in_domain_unknown_404(self, client) -> None:
        resp = client.get("/api/v1/registry/domains/ZupelnieFikcyjnaDomena9999")
        assert resp.status_code == 404

    def test_get_agents_in_domain_all_belong_to_domain(self, client) -> None:
        resp = client.get(
            "/api/v1/registry/domains/Silnik%20Unreal%20Engine?limit=50"
        )
        assert resp.status_code == 200
        for agent in resp.json()["agents"]:
            assert agent["domain"] == "Silnik Unreal Engine"


class TestRegistryChatAPI:
    """Testy endpointu POST /api/v1/registry/chat."""

    def test_chat_returns_200(self, client) -> None:
        resp = client.post(
            "/api/v1/registry/chat",
            json={"agent_id": "agent_0001", "message": "Przedstaw się krótko."},
        )
        assert resp.status_code == 200

    def test_chat_response_has_required_fields(self, client) -> None:
        resp = client.post(
            "/api/v1/registry/chat",
            json={"agent_id": "agent_0001", "message": "Co potrafisz?"},
        )
        data = resp.json()
        for field in ("agent_id", "display_name", "domain", "role",
                      "specialization", "category", "safety", "reply"):
            assert field in data, f"Brak pola: {field}"

    def test_chat_agent_id_matches_request(self, client) -> None:
        resp = client.post(
            "/api/v1/registry/chat",
            json={"agent_id": "agent_55555", "message": "Jakie masz umiejętności?"},
        )
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent_55555"

    def test_chat_display_name_not_empty(self, client) -> None:
        resp = client.post(
            "/api/v1/registry/chat",
            json={"agent_id": "agent_10000", "message": "Podaj przykład kodu."},
        )
        assert resp.json()["display_name"] != ""

    def test_chat_unknown_agent_404(self, client) -> None:
        resp = client.post(
            "/api/v1/registry/chat",
            json={"agent_id": "agent_99999", "message": "Hello!"},
        )
        assert resp.status_code == 404

    def test_chat_with_coding_agent(self, client) -> None:
        # Find an agent in Python Programming domain via API
        domain_resp = client.get(
            "/api/v1/registry/domains/Python%20Programming?limit=1"
        )
        agent_id = domain_resp.json()["agents"][0]["agent_id"]
        chat_resp = client.post(
            "/api/v1/registry/chat",
            json={"agent_id": agent_id, "message": "Napisz przykładową funkcję Python."},
        )
        assert chat_resp.status_code == 200
        data = chat_resp.json()
        assert data["domain"] == "Python Programming"
        assert data["reply"] != ""
