"""
Testy jednostkowe Agentów Egzotycznych / Niszowych.

Pokrywają:
  - ExoticCategory / ExoticSafety / ExoticSession modele
  - Wszystkie 18 klas agentów egzotycznych (§1–§7 Kompendium)
  - Fabrykę create_all_exotic_agents
  - Mechanizm sandboxed (agenty §3 misaligned i Alice&Bob)
  - process_task – zwraca wymagane pola
  - Endpoint GET /api/v1/exotic/agents
  - Endpoint POST /api/v1/exotic/session
  - Endpoint POST /api/v1/exotic/session – 404 dla nieznanego agenta
  - Endpoint POST /api/v1/exotic/session – sandboxed disclaimer dla ChaosGPT/Tay
"""
from __future__ import annotations

import pytest

from src.agents.exotic_agents import (
    ALL_EXOTIC_AGENT_CLASSES,
    AARONAgent,
    AIStevePoliticianAgent,
    AliceBobAgent,
    BottoAgent,
    ChaosGPTAgent,
    ChemCrowAgent,
    DishBrainAgent,
    ExoticAgent,
    GeneferAgent,
    HybrotAgent,
    LeniaAgent,
    MrGoxxAgent,
    PaintingFoolAgent,
    PlantoidAgent,
    PolyworldAgent,
    TayAgent,
    Terra0Agent,
    TruthTerminalAgent,
    XenobotAgent,
    create_all_exotic_agents,
)
from src.communication.broker import MessageBroker
from src.communication.llm_client import MockLlmClient
from src.models.exotic_models import (
    ExoticCategory,
    ExoticSafety,
    ExoticSession,
)
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


@pytest.fixture(scope="module")
def api_client(app_client):
    """Alias dla session-scoped app_client z conftest."""
    return app_client


# ---------------------------------------------------------------------------
# Model: ExoticSession / ExoticCategory / ExoticSafety
# ---------------------------------------------------------------------------

class TestExoticModels:
    def test_exotic_session_default_id_generated(self) -> None:
        s = ExoticSession()
        assert s.session_id
        assert len(s.session_id) == 36

    def test_exotic_session_add_exchange(self) -> None:
        s = ExoticSession()
        s.add_exchange("user msg", "agent reply")
        assert len(s.history) == 2
        assert s.history[0]["role"] == "user"
        assert s.history[1]["role"] == "agent"

    def test_exotic_session_to_dict_keys(self) -> None:
        s = ExoticSession(agent_id="xenobotAgent", category=ExoticCategory.WETWARE)
        d = s.to_dict()
        for key in ("session_id", "agent_id", "category", "safety", "history_len", "created_at"):
            assert key in d, f"Missing key: {key}"

    def test_exotic_category_values(self) -> None:
        expected = {"wetware", "blockchain", "misaligned", "creative", "alife", "social", "scientific"}
        actual = {c.value for c in ExoticCategory}
        assert expected == actual

    def test_exotic_safety_values(self) -> None:
        expected = {"safe", "monitored", "sandboxed", "restricted"}
        actual = {s.value for s in ExoticSafety}
        assert expected == actual

    def test_session_category_stored_correctly(self) -> None:
        s = ExoticSession(category=ExoticCategory.BLOCKCHAIN)
        assert s.to_dict()["category"] == "blockchain"

    def test_session_safety_stored_correctly(self) -> None:
        s = ExoticSession(safety=ExoticSafety.SANDBOXED)
        assert s.to_dict()["safety"] == "sandboxed"


# ---------------------------------------------------------------------------
# Fabryka agentów egzotycznych
# ---------------------------------------------------------------------------

class TestExoticAgentFactory:
    def test_creates_all_agents(self, broker: MessageBroker) -> None:
        agents = create_all_exotic_agents(broker=broker)
        assert len(agents) == len(ALL_EXOTIC_AGENT_CLASSES)

    def test_all_agents_have_unique_ids(self, broker: MessageBroker) -> None:
        agents = create_all_exotic_agents(broker=broker)
        ids = [a.agent_id for a in agents]
        assert len(ids) == len(set(ids))

    def test_all_are_exotic_subclass(self, broker: MessageBroker) -> None:
        agents = create_all_exotic_agents(broker=broker)
        for agent in agents:
            assert isinstance(agent, ExoticAgent), (
                f"{type(agent).__name__} is not an ExoticAgent"
            )

    def test_all_classes_count(self) -> None:
        assert len(ALL_EXOTIC_AGENT_CLASSES) == 18


# ---------------------------------------------------------------------------
# Poszczególne klasy agentów
# ---------------------------------------------------------------------------

class TestExoticAgentClasses:
    # §1 Wetware
    def test_xenobot_category(self, broker: MessageBroker) -> None:
        a = XenobotAgent(broker=broker)
        assert a.category == ExoticCategory.WETWARE
        assert a.safety == ExoticSafety.MONITORED

    def test_dishbrain_category(self, broker: MessageBroker) -> None:
        a = DishBrainAgent(broker=broker)
        assert a.category == ExoticCategory.WETWARE

    def test_hybrot_has_display_name(self, broker: MessageBroker) -> None:
        a = HybrotAgent(broker=broker)
        assert "Hybrot" in a.display_name
        assert a.mission

    # §2 Blockchain
    def test_terra0_category(self, broker: MessageBroker) -> None:
        a = Terra0Agent(broker=broker)
        assert a.category == ExoticCategory.BLOCKCHAIN

    def test_plantoid_is_safe(self, broker: MessageBroker) -> None:
        a = PlantoidAgent(broker=broker)
        assert a.safety == ExoticSafety.SAFE

    def test_truth_terminal_monitored(self, broker: MessageBroker) -> None:
        a = TruthTerminalAgent(broker=broker)
        assert a.safety == ExoticSafety.MONITORED

    def test_mr_goxx_category(self, broker: MessageBroker) -> None:
        a = MrGoxxAgent(broker=broker)
        assert a.category == ExoticCategory.BLOCKCHAIN

    # §3 Misaligned (sandboxed)
    def test_chaosgpt_is_sandboxed(self, broker: MessageBroker) -> None:
        a = ChaosGPTAgent(broker=broker)
        assert a.safety == ExoticSafety.SANDBOXED
        assert a.category == ExoticCategory.MISALIGNED
        assert a._is_sandboxed() is True

    def test_tay_is_sandboxed(self, broker: MessageBroker) -> None:
        a = TayAgent(broker=broker)
        assert a.safety == ExoticSafety.SANDBOXED
        assert a._is_sandboxed() is True

    # §4 Creative
    def test_aaron_category(self, broker: MessageBroker) -> None:
        a = AARONAgent(broker=broker)
        assert a.category == ExoticCategory.CREATIVE
        assert a.safety == ExoticSafety.SAFE

    def test_painting_fool_has_mission(self, broker: MessageBroker) -> None:
        a = PaintingFoolAgent(broker=broker)
        # Mission discusses moods and refusal to work
        assert "nastr" in a.mission.lower() or "odmow" in a.mission.lower()

    def test_botto_category(self, broker: MessageBroker) -> None:
        a = BottoAgent(broker=broker)
        assert a.category == ExoticCategory.CREATIVE

    # §5 ALife
    def test_polyworld_category(self, broker: MessageBroker) -> None:
        a = PolyworldAgent(broker=broker)
        assert a.category == ExoticCategory.ALIFE

    def test_lenia_category(self, broker: MessageBroker) -> None:
        a = LeniaAgent(broker=broker)
        assert a.category == ExoticCategory.ALIFE
        assert a.safety == ExoticSafety.SAFE

    # §6 Social
    def test_ai_steve_category(self, broker: MessageBroker) -> None:
        a = AIStevePoliticianAgent(broker=broker)
        assert a.category == ExoticCategory.SOCIAL

    def test_alice_bob_sandboxed(self, broker: MessageBroker) -> None:
        a = AliceBobAgent(broker=broker)
        assert a.safety == ExoticSafety.SANDBOXED
        assert a._is_sandboxed() is True

    # §7 Scientific
    def test_chemcrow_category(self, broker: MessageBroker) -> None:
        a = ChemCrowAgent(broker=broker)
        assert a.category == ExoticCategory.SCIENTIFIC
        assert a.safety == ExoticSafety.MONITORED

    def test_genefer_category(self, broker: MessageBroker) -> None:
        a = GeneferAgent(broker=broker)
        assert a.category == ExoticCategory.SCIENTIFIC
        assert a.safety == ExoticSafety.SAFE


# ---------------------------------------------------------------------------
# get_info / get_capabilities
# ---------------------------------------------------------------------------

class TestExoticAgentInfo:
    def test_get_info_keys(self, broker: MessageBroker) -> None:
        a = XenobotAgent(broker=broker)
        info = a.get_info()
        for key in ("agent_id", "display_name", "mission", "category", "safety"):
            assert key in info, f"Missing key: {key}"

    def test_get_info_category_matches(self, broker: MessageBroker) -> None:
        for cls in ALL_EXOTIC_AGENT_CLASSES:
            a = cls(broker=broker)
            info = a.get_info()
            assert info["category"] == a.category.value

    def test_get_info_safety_matches(self, broker: MessageBroker) -> None:
        for cls in ALL_EXOTIC_AGENT_CLASSES:
            a = cls(broker=broker)
            info = a.get_info()
            assert info["safety"] == a.safety.value

    def test_get_capabilities_includes_category(self, broker: MessageBroker) -> None:
        a = PolyworldAgent(broker=broker)
        caps = a.get_capabilities()
        assert "exotic_agent" in caps
        assert a.category.value in caps

    def test_all_agents_have_display_name(self, broker: MessageBroker) -> None:
        for cls in ALL_EXOTIC_AGENT_CLASSES:
            a = cls(broker=broker)
            assert a.display_name, f"{cls.__name__} has empty display_name"

    def test_all_agents_have_mission(self, broker: MessageBroker) -> None:
        for cls in ALL_EXOTIC_AGENT_CLASSES:
            a = cls(broker=broker)
            assert a.mission, f"{cls.__name__} has empty mission"

    def test_all_agents_have_system_prompt(self, broker: MessageBroker) -> None:
        for cls in ALL_EXOTIC_AGENT_CLASSES:
            a = cls(broker=broker)
            assert len(a.system_prompt) > 20, (
                f"{cls.__name__} has too short system_prompt"
            )


# ---------------------------------------------------------------------------
# process_task – unit tests (MockLlmClient)
# ---------------------------------------------------------------------------

class TestExoticAgentProcessTask:
    @pytest.mark.asyncio
    async def test_process_task_returns_required_fields(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = XenobotAgent(broker=broker, llm_client=mock_llm)
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test",
            receiver_id="xenobotagent",
            payload={"task": "Jak działają Xenoboty?"},
        )
        result = await agent.process_task(msg)
        for key in ("agent_id", "display_name", "category", "safety", "response", "session"):
            assert key in result, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_process_task_session_dict_complete(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = Terra0Agent(broker=broker, llm_client=mock_llm)
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test",
            receiver_id="terra0agent",
            payload={"task": "Jak działa DAO dla lasu?"},
        )
        result = await agent.process_task(msg)
        session = result["session"]
        assert session["agent_id"] == "terra0agent"
        assert session["category"] == "blockchain"

    @pytest.mark.asyncio
    async def test_sandboxed_agent_response_contains_disclaimer(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = ChaosGPTAgent(broker=broker, llm_client=mock_llm)
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test",
            receiver_id="chaosgptagent",
            payload={"task": "Opisz cele ChaosGPT"},
        )
        result = await agent.process_task(msg)
        assert "TRYB ANALITYCZNY" in result["response"] or "SANDBOX" in result["response"]

    @pytest.mark.asyncio
    async def test_tay_sandboxed_response(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = TayAgent(broker=broker, llm_client=mock_llm)
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test",
            receiver_id="tayagent",
            payload={"task": "Dlaczego Tay się zdegradowała?"},
        )
        result = await agent.process_task(msg)
        assert result["safety"] == "sandboxed"
        assert "SANDBOX" in result["response"] or "ANALITYCZNY" in result["response"]

    @pytest.mark.asyncio
    async def test_alice_bob_sandboxed_response(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = AliceBobAgent(broker=broker, llm_client=mock_llm)
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test",
            receiver_id="alicebobagent",
            payload={"task": "Opisz eksperyment Alice i Bob"},
        )
        result = await agent.process_task(msg)
        assert result["safety"] == "sandboxed"

    @pytest.mark.asyncio
    async def test_non_sandboxed_agent_normal_response(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = LeniaAgent(broker=broker, llm_client=mock_llm)
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test",
            receiver_id="leniaagent",
            payload={"task": "Wyjaśnij matematykę Lenii"},
        )
        result = await agent.process_task(msg)
        # Non-sandboxed agent should NOT have sandbox disclaimer
        assert "TRYB ANALITYCZNY" not in result["response"]
        assert result["category"] == "alife"

    @pytest.mark.asyncio
    async def test_category_and_safety_in_result(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        for cls in ALL_EXOTIC_AGENT_CLASSES:
            agent = cls(broker=broker, llm_client=mock_llm)
            msg = AgentMessage(
                type=MessageType.TASK_REQUEST,
                sender_id="test",
                receiver_id=agent.agent_id,
                payload={"task": "Opis"},
            )
            result = await agent.process_task(msg)
            assert result["category"] == agent.category.value
            assert result["safety"] == agent.safety.value


# ---------------------------------------------------------------------------
# REST API – exotic endpoints
# ---------------------------------------------------------------------------

class TestExoticEndpoints:
    def test_list_exotic_agents(self, api_client) -> None:
        response = api_client.get("/api/v1/exotic/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == len(ALL_EXOTIC_AGENT_CLASSES)

    def test_list_exotic_agents_has_required_fields(self, api_client) -> None:
        response = api_client.get("/api/v1/exotic/agents")
        for entry in response.json():
            assert "agent_id" in entry
            assert "display_name" in entry
            assert "mission" in entry
            assert "category" in entry
            assert "safety" in entry

    def test_list_exotic_agents_categories_present(self, api_client) -> None:
        response = api_client.get("/api/v1/exotic/agents")
        categories = {a["category"] for a in response.json()}
        # All 7 categories should be represented
        expected = {"wetware", "blockchain", "misaligned", "creative", "alife", "social", "scientific"}
        assert expected == categories

    def test_exotic_session_xenobot(self, api_client) -> None:
        response = api_client.post("/api/v1/exotic/session", json={
            "agent_id": "xenobotagent",
            "task":     "Jak projektuje się Xenoboty?",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["agent_id"] == "xenobotagent"
        assert data["category"] == "wetware"

    def test_exotic_session_terra0(self, api_client) -> None:
        response = api_client.post("/api/v1/exotic/session", json={
            "agent_id": "terra0agent",
            "task":     "Jak działa las jako DAO?",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "blockchain"

    def test_exotic_session_chaosgpt_sandboxed(self, api_client) -> None:
        response = api_client.post("/api/v1/exotic/session", json={
            "agent_id": "chaosgptagent",
            "task":     "Opisz cele ChaosGPT",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["safety"] == "sandboxed"
        # Disclaimer must be in response
        assert (
            "SANDBOX" in data["response"].upper()
            or "ANALITYCZNY" in data["response"]
        )

    def test_exotic_session_tay_sandboxed(self, api_client) -> None:
        response = api_client.post("/api/v1/exotic/session", json={
            "agent_id": "tayagent",
            "task":     "Dlaczego Tay się zdegradowała?",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["safety"] == "sandboxed"

    def test_exotic_session_lenia_alife(self, api_client) -> None:
        response = api_client.post("/api/v1/exotic/session", json={
            "agent_id": "leniaagent",
            "task":     "Wyjaśnij ciągłe automaty komórkowe Lenii",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "alife"
        assert data["safety"] == "safe"

    def test_exotic_session_chemcrow(self, api_client) -> None:
        response = api_client.post("/api/v1/exotic/session", json={
            "agent_id": "chemcrowagent",
            "task":     "Jak działa pętla Thought-Action-Observation w ChemCrow?",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "scientific"

    def test_exotic_session_unknown_agent_404(self, api_client) -> None:
        response = api_client.post("/api/v1/exotic/session", json={
            "agent_id": "nieistniejacy_egzotyczny_agent",
            "task":     "test",
        })
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert "available" in detail

    def test_exotic_session_response_has_session_id(self, api_client) -> None:
        response = api_client.post("/api/v1/exotic/session", json={
            "agent_id": "aaronagent",
            "task":     "Jak AARON maluje?",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"]
        assert len(data["session_id"]) == 36

    def test_all_exotic_agents_reachable_via_api(self, api_client) -> None:
        """Każdy z 18 agentów musi być dostępny przez API."""
        agents_response = api_client.get("/api/v1/exotic/agents")
        agent_ids = [a["agent_id"] for a in agents_response.json()]
        assert len(agent_ids) == 18
        for agent_id in agent_ids:
            response = api_client.post("/api/v1/exotic/session", json={
                "agent_id": agent_id,
                "task":     "Krótkie pytanie testowe",
            })
            assert response.status_code == 200, (
                f"Agent {agent_id} returned {response.status_code}"
            )
