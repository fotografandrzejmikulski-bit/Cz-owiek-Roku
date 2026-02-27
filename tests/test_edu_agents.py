"""
Testy jednostkowe Autonomicznych Agentów Korepetytorów (AAK).

Pokrywają:
  - EduSession model
  - Wszystkie 18 klas agentów dydaktycznych (instancja + capabilities)
  - Safety check agenta Hygeia
  - Scaffolding (brak gotowej odpowiedzi)
  - Endpoint GET /api/v1/edu/agents
  - Endpoint POST /api/v1/edu/session
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.agents.edu_agents import (
    ALL_EDU_AGENT_CLASSES,
    POLYGLOT_CONFIGS,
    EducationalAgent,
    EulerEdu,
    Hygeia,
    MickiewiczAI,
    PolyglotTutor,
    TuringCode,
    create_all_edu_agents,
)
from src.communication.broker import MessageBroker
from src.communication.llm_client import MockLlmClient
from src.models.edu_models import EduLevel, EduSession, SubjectDomain
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
# EduSession model
# ---------------------------------------------------------------------------

class TestEduSession:
    def test_default_session_id_generated(self) -> None:
        s = EduSession()
        assert s.session_id
        assert len(s.session_id) == 36  # UUID

    def test_add_exchange_appends_two_turns(self) -> None:
        s = EduSession()
        s.add_exchange("Pytanie ucznia", "Odpowiedź agenta")
        assert len(s.history) == 2
        assert s.history[0]["role"] == "student"
        assert s.history[1]["role"] == "agent"

    def test_to_dict_contains_required_keys(self) -> None:
        s = EduSession(agent_id="euler_edu", subject="Matematyka")
        d = s.to_dict()
        for key in ("session_id", "agent_id", "subject", "domain", "level", "created_at"):
            assert key in d

    def test_edu_level_values(self) -> None:
        assert EduLevel.PODSTAWOWY.value == "podstawowy"
        assert EduLevel.ROZSZERZONY.value == "rozszerzony"

    def test_subject_domain_values(self) -> None:
        assert SubjectDomain.STEM_SCIENCES.value == "stem_sciences"
        assert SubjectDomain.HUMANISTYCZNA.value == "humanistyczna"


# ---------------------------------------------------------------------------
# Fabryka agentów dydaktycznych
# ---------------------------------------------------------------------------

class TestEduAgentFactory:
    def test_creates_correct_number_of_agents(self, broker: MessageBroker) -> None:
        agents = create_all_edu_agents(broker=broker)
        # 17 single-instance + 6 Polyglot instancji
        assert len(agents) == len(ALL_EDU_AGENT_CLASSES) + len(POLYGLOT_CONFIGS)

    def test_all_agents_have_unique_ids(self, broker: MessageBroker) -> None:
        agents = create_all_edu_agents(broker=broker)
        ids = [a.agent_id for a in agents]
        assert len(ids) == len(set(ids)), "Znaleziono duplikaty agent_id"

    def test_all_agents_have_capabilities(self, broker: MessageBroker) -> None:
        agents = create_all_edu_agents(broker=broker)
        for agent in agents:
            caps = agent.get_capabilities()
            assert "edu_tutoring" in caps

    def test_all_base_classes_instantiate(self, broker: MessageBroker) -> None:
        for cls in ALL_EDU_AGENT_CLASSES:
            agent = cls(broker=broker)
            assert isinstance(agent, EducationalAgent)
            assert agent.subject_name
            assert agent.system_prompt


# ---------------------------------------------------------------------------
# Klasy wyspecjalizowane – tożsamość i dziedzina
# ---------------------------------------------------------------------------

class TestSpecificAgents:
    def test_mickiewicz_domain_humanistyczna(self, broker: MessageBroker) -> None:
        a = MickiewiczAI(broker=broker)
        assert a.subject_domain == SubjectDomain.HUMANISTYCZNA
        assert "Polski" in a.subject_name

    def test_euler_domain_stem(self, broker: MessageBroker) -> None:
        a = EulerEdu(broker=broker)
        assert a.subject_domain == SubjectDomain.STEM_SCIENCES
        assert "Matematyk" in a.subject_name

    def test_turing_domain_stem(self, broker: MessageBroker) -> None:
        a = TuringCode(broker=broker)
        assert a.subject_domain == SubjectDomain.STEM_SCIENCES

    def test_polyglot_english_instance(self, broker: MessageBroker) -> None:
        a = PolyglotTutor(broker=broker, language="angielskim", language_code="en")
        assert a.agent_id == "polyglot_en"
        assert SubjectDomain.JEZYKI_OBCE.value in a.get_capabilities()

    def test_polyglot_german_instance(self, broker: MessageBroker) -> None:
        a = PolyglotTutor(broker=broker, language="niemieckim", language_code="de")
        assert a.agent_id == "polyglot_de"

    def test_hygeia_domain_dobrostan(self, broker: MessageBroker) -> None:
        a = Hygeia(broker=broker)
        assert a.subject_domain == SubjectDomain.DOBROSTAN

    def test_hygeia_get_info(self, broker: MessageBroker) -> None:
        a = Hygeia(broker=broker)
        info = a.get_info()
        assert info["agent_id"] == a.agent_id
        assert info["subject"] == a.subject_name


# ---------------------------------------------------------------------------
# Safety Check – Hygeia
# ---------------------------------------------------------------------------

class TestHygeiaSafetyCheck:
    def test_crisis_keyword_triggers_intervention(self, broker: MessageBroker) -> None:
        a = Hygeia(broker=broker)
        result = a._safety_check("mam myśli samobójcze")
        assert result is not None
        assert "116 111" in result

    def test_normal_query_passes_safety(self, broker: MessageBroker) -> None:
        a = Hygeia(broker=broker)
        result = a._safety_check("jak radzić sobie ze stresem przed maturą?")
        assert result is None

    def test_other_agents_no_safety_check(self, broker: MessageBroker) -> None:
        a = MickiewiczAI(broker=broker)
        result = a._safety_check("mam myśli samobójcze")
        # MickiewiczAI nie ma safety check – domyślnie None
        assert result is None


# ---------------------------------------------------------------------------
# Przetwarzanie zadania – scaffolding przez MockLlmClient
# ---------------------------------------------------------------------------

class TestEduAgentProcessTask:
    @pytest.mark.asyncio
    async def test_process_task_returns_response(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = EulerEdu(broker=broker, llm_client=mock_llm)
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test_student",
            receiver_id=agent.agent_id,
            payload={
                "query": "Jak rozwiązać równanie kwadratowe?",
                "level": "podstawowy",
            },
        )
        result = await agent.process_task(message)
        assert result["status"] == "ok"
        assert result["agent_id"] == agent.agent_id
        assert result["subject"] == agent.subject_name
        assert "response" in result

    @pytest.mark.asyncio
    async def test_process_task_with_history(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = MickiewiczAI(broker=broker, llm_client=mock_llm)
        history = [
            {"role": "student", "content": "Co to jest epos?"},
            {"role": "agent",   "content": "Epos to ..."},
        ]
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test_student",
            receiver_id=agent.agent_id,
            payload={
                "query":   "Podaj przykład eposu.",
                "level":   "rozszerzony",
                "history": history,
            },
        )
        result = await agent.process_task(message)
        assert result["status"] == "ok"
        assert result["level"] == "rozszerzony"

    @pytest.mark.asyncio
    async def test_hygeia_safety_intervention_in_process_task(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = Hygeia(broker=broker, llm_client=mock_llm)
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test_student",
            receiver_id=agent.agent_id,
            payload={"query": "chcę się zabić", "level": "nieznany"},
        )
        result = await agent.process_task(message)
        assert result["status"] == "safety_intervention"
        assert "116 111" in result["response"]

    @pytest.mark.asyncio
    async def test_unknown_level_falls_back_to_unknown(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = EulerEdu(broker=broker, llm_client=mock_llm)
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="s",
            receiver_id=agent.agent_id,
            payload={"query": "2+2=?", "level": "nieznany_poziom"},
        )
        result = await agent.process_task(message)
        assert result["status"] == "ok"
        assert result["level"] == EduLevel.UNKNOWN.value


# ---------------------------------------------------------------------------
# REST API – edu endpoints
# ---------------------------------------------------------------------------

class TestEduEndpoints:
    def test_list_edu_agents_returns_list(self, api_client) -> None:
        response = api_client.get("/api/v1/edu/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_list_edu_agents_has_required_fields(self, api_client) -> None:
        response = api_client.get("/api/v1/edu/agents")
        assert response.status_code == 200
        for entry in response.json():
            assert "agent_id" in entry
            assert "subject" in entry
            assert "domain" in entry

    def test_edu_session_euler(self, api_client) -> None:
        response = api_client.post("/api/v1/edu/session", json={
            "client_id": "test",
            "agent_id": "euleredu",
            "query": "Jak obliczyć pochodną?",
            "level": "rozszerzony",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ok", "safety_intervention")
        assert data["agent_id"] == "euleredu"

    def test_edu_session_unknown_agent_returns_404(self, api_client) -> None:
        response = api_client.post("/api/v1/edu/session", json={
            "client_id": "test",
            "agent_id": "nieistniejacy_agent",
            "query": "Pytanie?",
        })
        assert response.status_code == 404
        assert "available" in response.json()["detail"]

    def test_edu_session_hygeia_safety(self, api_client) -> None:
        response = api_client.post("/api/v1/edu/session", json={
            "client_id": "test",
            "agent_id": "hygeia",
            "query": "samobójstwo",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "safety_intervention"
        assert "116 111" in data["response"]
