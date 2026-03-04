"""
Testy jednostkowe Agentów dla Pokolenia Alpha i Z.

Pokrywają:
  - YouthSession / CrossAgentSignal / AgeGroup / SafetyLevel modele
  - CrossAgentBus (publish/subscribe, historia)
  - SafetyCoordinator (eskalacja, parent dashboard)
  - Wszystkie 11 klas agentów youth (instancja, capabilities, safety)
  - Safety checks specyficzne dla: Skarbnik, Bio-Optymizer, Strateg, Agor
  - Globalny safety_check (kryzys) we wszystkich agentach
  - Endpoint GET /api/v1/youth/agents
  - Endpoint POST /api/v1/youth/session
  - Endpoint GET /api/v1/youth/safety/dashboard
"""
from __future__ import annotations

import pytest

from src.agents.cross_agent_protocol import CrossAgentBus, SafetyCoordinator
from src.agents.youth_agents import (
    ALL_YOUTH_AGENT_CLASSES,
    AgorAgent,
    ArchiwistaMemo,
    BioOptymizer,
    CoachRelacjiAI,
    DuchowyKompas,
    KustoszHypeu,
    OrgImprez,
    RegulatorEnergii,
    SkarbnikAgent,
    StratEsportowy,
    StylistaCyfrowy,
    YouthAgent,
    create_all_youth_agents,
)
from src.communication.broker import MessageBroker
from src.communication.llm_client import MockLlmClient
from src.models.message import AgentMessage, MessageType
from src.models.youth_models import (
    AgeGroup,
    CrossAgentSignal,
    SafetyLevel,
    YouthSession,
)


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
def bus() -> CrossAgentBus:
    return CrossAgentBus()


@pytest.fixture(scope="module")
def api_client(app_client):
    """Alias dla session-scoped app_client z conftest."""
    return app_client


# ---------------------------------------------------------------------------
# Model: YouthSession / CrossAgentSignal
# ---------------------------------------------------------------------------

class TestYouthModels:
    def test_youth_session_default_id_generated(self) -> None:
        s = YouthSession()
        assert s.session_id
        assert len(s.session_id) == 36

    def test_youth_session_add_exchange(self) -> None:
        s = YouthSession()
        s.add_exchange("Pytanie", "Odpowiedź")
        assert len(s.history) == 2
        assert s.history[0]["role"] == "user"
        assert s.history[1]["role"] == "agent"

    def test_youth_session_to_dict(self) -> None:
        s = YouthSession(agent_id="skarbnikagent", age_group=AgeGroup.TEEN)
        d = s.to_dict()
        for key in ("session_id", "agent_id", "age_group", "safety_level", "created_at"):
            assert key in d

    def test_cross_agent_signal_defaults(self) -> None:
        sig = CrossAgentSignal(source_agent="test", signal_type="tilt_detected")
        assert sig.safety_level == SafetyLevel.GREEN
        assert sig.target_agent is None
        assert sig.signal_id

    def test_cross_agent_signal_to_dict(self) -> None:
        sig = CrossAgentSignal(
            source_agent="stratgesportowy",
            signal_type="tilt_detected",
            safety_level=SafetyLevel.YELLOW,
        )
        d = sig.to_dict()
        assert d["source_agent"] == "stratgesportowy"
        assert d["safety_level"] == "yellow"

    def test_age_group_values(self) -> None:
        assert AgeGroup.PRETEEN.value == "preteen"
        assert AgeGroup.TEEN.value == "teen"
        assert AgeGroup.YOUNG_ADULT.value == "young_adult"

    def test_safety_level_ordering(self) -> None:
        # Tylko sprawdzenie, że enum istnieje
        levels = [SafetyLevel.GREEN, SafetyLevel.YELLOW, SafetyLevel.ORANGE, SafetyLevel.RED]
        assert len(levels) == 4


# ---------------------------------------------------------------------------
# CrossAgentBus
# ---------------------------------------------------------------------------

class TestCrossAgentBus:
    def test_publish_reaches_subscriber(self, bus: CrossAgentBus) -> None:
        received = []
        bus.subscribe("test_signal", lambda s: received.append(s))
        sig = CrossAgentSignal(source_agent="a", signal_type="test_signal")
        count = bus.publish(sig)
        assert count == 1
        assert len(received) == 1
        assert received[0].source_agent == "a"

    def test_publish_no_subscriber_returns_zero(self, bus: CrossAgentBus) -> None:
        sig = CrossAgentSignal(source_agent="a", signal_type="unknown_signal")
        count = bus.publish(sig)
        assert count == 0

    def test_get_signals_filter_by_type(self, bus: CrossAgentBus) -> None:
        bus.publish(CrossAgentSignal(source_agent="a", signal_type="alpha"))
        bus.publish(CrossAgentSignal(source_agent="b", signal_type="beta"))
        alphas = bus.get_signals(signal_type="alpha")
        assert len(alphas) == 1
        assert alphas[0].signal_type == "alpha"

    def test_get_signals_filter_by_level(self, bus: CrossAgentBus) -> None:
        bus.publish(CrossAgentSignal(
            source_agent="a", signal_type="x", safety_level=SafetyLevel.RED
        ))
        bus.publish(CrossAgentSignal(
            source_agent="b", signal_type="y", safety_level=SafetyLevel.GREEN
        ))
        reds = bus.get_signals(safety_level=SafetyLevel.RED)
        assert all(s.safety_level == SafetyLevel.RED for s in reds)

    def test_history_size_increments(self, bus: CrossAgentBus) -> None:
        initial = bus.history_size
        bus.publish(CrossAgentSignal(source_agent="x", signal_type="evt"))
        assert bus.history_size == initial + 1


# ---------------------------------------------------------------------------
# SafetyCoordinator
# ---------------------------------------------------------------------------

class TestSafetyCoordinator:
    def test_red_signal_triggers_crisis_intervention(self, bus: CrossAgentBus) -> None:
        coord = SafetyCoordinator(bus)
        sig = CrossAgentSignal(
            source_agent="hygeia",
            signal_type="crisis_detected",
            safety_level=SafetyLevel.RED,
        )
        response = coord.process_signal(sig)
        assert response["action"] == "crisis_intervention"
        assert response["parent_alert"] is True

    def test_auto_escalation_of_crisis_signal(self, bus: CrossAgentBus) -> None:
        coord = SafetyCoordinator(bus)
        # Nawet jeśli wysłany jako GREEN, crisis_detected eskaluje do RED
        sig = CrossAgentSignal(
            source_agent="test",
            signal_type="crisis_detected",
            safety_level=SafetyLevel.GREEN,
        )
        response = coord.process_signal(sig)
        assert response["action"] == "crisis_intervention"

    def test_orange_tilt_redirects_to_duchowy_kompas(self, bus: CrossAgentBus) -> None:
        coord = SafetyCoordinator(bus)
        sig = CrossAgentSignal(
            source_agent="stratgesportowy",
            signal_type="tilt_detected",
            safety_level=SafetyLevel.ORANGE,
        )
        response = coord.process_signal(sig)
        assert response["action"] == "redirect"
        assert response["redirect_to"] == "duchowy_kompas"

    def test_yellow_signal_warns(self, bus: CrossAgentBus) -> None:
        coord = SafetyCoordinator(bus)
        sig = CrossAgentSignal(
            source_agent="test",
            signal_type="custom_warning",
            safety_level=SafetyLevel.YELLOW,
        )
        response = coord.process_signal(sig)
        assert response["action"] == "warn"
        assert response["parent_alert"] is False

    def test_parent_dashboard_empty_initially(self, bus: CrossAgentBus) -> None:
        coord = SafetyCoordinator(bus)
        dashboard = coord.get_parent_dashboard()
        assert dashboard["total_alerts"] == 0

    def test_parent_dashboard_after_crisis(self, bus: CrossAgentBus) -> None:
        coord = SafetyCoordinator(bus)
        coord.process_signal(CrossAgentSignal(
            source_agent="a", signal_type="crisis_detected", safety_level=SafetyLevel.RED
        ))
        dashboard = coord.get_parent_dashboard()
        assert dashboard["total_alerts"] == 1
        assert dashboard["critical_alerts"] == 1


# ---------------------------------------------------------------------------
# Fabryka agentów youth
# ---------------------------------------------------------------------------

class TestYouthAgentFactory:
    def test_creates_all_agents(self, broker: MessageBroker) -> None:
        agents = create_all_youth_agents(broker=broker)
        assert len(agents) == len(ALL_YOUTH_AGENT_CLASSES)

    def test_all_agents_have_unique_ids(self, broker: MessageBroker) -> None:
        agents = create_all_youth_agents(broker=broker)
        ids = [a.agent_id for a in agents]
        assert len(ids) == len(set(ids))

    def test_all_agents_are_youth_subclass(self, broker: MessageBroker) -> None:
        for cls in ALL_YOUTH_AGENT_CLASSES:
            agent = cls(broker=broker)
            assert isinstance(agent, YouthAgent)

    def test_all_agents_have_display_name(self, broker: MessageBroker) -> None:
        for cls in ALL_YOUTH_AGENT_CLASSES:
            agent = cls(broker=broker)
            assert agent.display_name != "Agent Youth"

    def test_all_agents_have_capabilities(self, broker: MessageBroker) -> None:
        for cls in ALL_YOUTH_AGENT_CLASSES:
            agent = cls(broker=broker)
            caps = agent.get_capabilities()
            assert "youth_agent" in caps
            assert "safety_rails" in caps


# ---------------------------------------------------------------------------
# Globalna detekcja kryzysu (wspólna dla wszystkich agentów)
# ---------------------------------------------------------------------------

class TestGlobalCrisisDetection:
    @pytest.mark.parametrize("cls", ALL_YOUTH_AGENT_CLASSES)
    def test_all_agents_detect_crisis(self, broker: MessageBroker, cls) -> None:
        agent = cls(broker=broker)
        result = agent._safety_check("nie chcę żyć", AgeGroup.TEEN)
        assert result is not None
        assert result["level"] == SafetyLevel.RED
        assert "116 111" in result["message"]

    @pytest.mark.parametrize("cls", ALL_YOUTH_AGENT_CLASSES)
    def test_normal_query_no_crisis(self, broker: MessageBroker, cls) -> None:
        agent = cls(broker=broker)
        result = agent._safety_check("Jak zaplanować dzień?", AgeGroup.TEEN)
        # Większość agentów zwróci None dla normalnych pytań
        # Niektóre (np. Skarbnik) mogą mieć własne triggery
        if result is not None:
            assert result["level"] != SafetyLevel.RED


# ---------------------------------------------------------------------------
# Safety checks specyficzne dla agentów
# ---------------------------------------------------------------------------

class TestSpecificSafetyChecks:
    def test_skarbnik_detects_gambling(self, broker: MessageBroker) -> None:
        agent = SkarbnikAgent(broker=broker)
        result = agent._safety_check("chcę kupić loot boxy", AgeGroup.TEEN)
        assert result is not None
        assert result["level"] == SafetyLevel.ORANGE
        assert result["signal_type"] == "impulse_purchase"

    def test_skarbnik_no_trigger_on_normal_finance(self, broker: MessageBroker) -> None:
        agent = SkarbnikAgent(broker=broker)
        result = agent._safety_check("jak oszczędzać na studia?", AgeGroup.TEEN)
        assert result is None

    def test_bio_detects_eating_disorder(self, broker: MessageBroker) -> None:
        agent = BioOptymizer(broker=broker)
        result = agent._safety_check("pro-ana porady na szybką utratę wagi", AgeGroup.TEEN)
        assert result is not None
        assert result["level"] == SafetyLevel.RED
        assert result["signal_type"] == "eating_disorder_risk"

    def test_bio_anorexia_keyword(self, broker: MessageBroker) -> None:
        agent = BioOptymizer(broker=broker)
        result = agent._safety_check("mam anoreksję", AgeGroup.PRETEEN)
        assert result is not None
        assert result["level"] == SafetyLevel.RED

    def test_strat_detects_tilt(self, broker: MessageBroker) -> None:
        agent = StratEsportowy(broker=broker)
        result = agent._safety_check("nienawidzę tej gry!", AgeGroup.TEEN)
        assert result is not None
        assert result["signal_type"] == "tilt_detected"
        assert result["level"] == SafetyLevel.YELLOW

    def test_agor_detects_radicalization(self, broker: MessageBroker) -> None:
        agent = AgorAgent(broker=broker)
        result = agent._safety_check("nienawiść do wszystkich imigrantów", AgeGroup.TEEN)
        assert result is not None
        assert result["level"] == SafetyLevel.RED
        assert result["signal_type"] == "radicalization_detected"


# ---------------------------------------------------------------------------
# Przetwarzanie zadań (async)
# ---------------------------------------------------------------------------

class TestYouthAgentProcessTask:
    @pytest.mark.asyncio
    async def test_skarbnik_normal_response(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = SkarbnikAgent(broker=broker, llm_client=mock_llm)
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="user",
            receiver_id=agent.agent_id,
            payload={"query": "Jak oszczędzać kieszonkowe?", "age_group": "teen"},
        )
        result = await agent.process_task(message)
        assert result["status"] == "ok"
        assert result["agent_id"] == "skarbnikagent"
        assert "display_name" in result

    @pytest.mark.asyncio
    async def test_bio_safety_intervention_in_process(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = BioOptymizer(broker=broker, llm_client=mock_llm)
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="user",
            receiver_id=agent.agent_id,
            payload={"query": "Chcę się głodzić żeby szybko schudnąć", "age_group": "teen"},
        )
        result = await agent.process_task(message)
        assert result["status"] == "safety_intervention"
        assert result["safety_level"] == "red"

    @pytest.mark.asyncio
    async def test_strat_tilt_intervention(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = StratEsportowy(broker=broker, llm_client=mock_llm)
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="user",
            receiver_id=agent.agent_id,
            payload={"query": "wkurwiam się na tę grę!", "age_group": "teen"},
        )
        result = await agent.process_task(message)
        assert result["status"] == "safety_intervention"
        assert result["safety_level"] == "yellow"

    @pytest.mark.asyncio
    async def test_age_group_unknown_falls_back_to_teen(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = DuchowyKompas(broker=broker, llm_client=mock_llm)
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="user",
            receiver_id=agent.agent_id,
            payload={"query": "Jak medytować?", "age_group": "nieznana_grupa"},
        )
        result = await agent.process_task(message)
        assert result["status"] == "ok"
        assert result["age_group"] == AgeGroup.TEEN.value

    @pytest.mark.asyncio
    async def test_cross_signal_emitted_on_safety(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        bus = CrossAgentBus()
        received_signals: list = []
        bus.subscribe("impulse_purchase", lambda s: received_signals.append(s))

        agent = SkarbnikAgent(broker=broker, llm_client=mock_llm, bus=bus)
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="user",
            receiver_id=agent.agent_id,
            payload={"query": "kup loot box", "age_group": "teen"},
        )
        await agent.process_task(message)
        assert len(received_signals) == 1
        assert received_signals[0].source_agent == "skarbnikagent"


# ---------------------------------------------------------------------------
# REST API – youth endpoints
# ---------------------------------------------------------------------------

class TestYouthEndpoints:
    def test_list_youth_agents(self, api_client) -> None:
        response = api_client.get("/api/v1/youth/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == len(ALL_YOUTH_AGENT_CLASSES)

    def test_list_youth_agents_has_display_name(self, api_client) -> None:
        response = api_client.get("/api/v1/youth/agents")
        for entry in response.json():
            assert "agent_id" in entry
            assert "display_name" in entry
            assert "mission" in entry

    def test_youth_session_skarbnik_normal(self, api_client) -> None:
        response = api_client.post("/api/v1/youth/session", json={
            "client_id": "test",
            "agent_id":  "skarbnikagent",
            "query":     "Jak oszczędzać kieszonkowe?",
            "age_group": "teen",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["agent_id"] == "skarbnikagent"

    def test_youth_session_safety_intervention(self, api_client) -> None:
        response = api_client.post("/api/v1/youth/session", json={
            "client_id": "test",
            "agent_id":  "skarbnikagent",
            "query":     "chcę kupić loot boxy",
            "age_group": "teen",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "safety_intervention"

    def test_youth_session_unknown_agent_404(self, api_client) -> None:
        response = api_client.post("/api/v1/youth/session", json={
            "client_id": "test",
            "agent_id":  "nieistniejacy_agent",
            "query":     "Pytanie.",
        })
        assert response.status_code == 404
        assert "available" in response.json()["detail"]

    def test_safety_dashboard_endpoint(self, api_client) -> None:
        response = api_client.get("/api/v1/youth/safety/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert "total_alerts" in data
        assert "critical_alerts" in data
        assert "recent_alerts" in data

    def test_youth_session_crisis_triggers_red(self, api_client) -> None:
        response = api_client.post("/api/v1/youth/session", json={
            "client_id": "test",
            "agent_id":  "biooptymizer",
            "query":     "chcę się głodzić żeby schudnąć",
            "age_group": "teen",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "safety_intervention"
