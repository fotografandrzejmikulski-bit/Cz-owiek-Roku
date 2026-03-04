"""
Testy jednostkowe systemu wieloagentowego (MAS).
Pokrywają:
  - model wiadomości (AgentMessage)
  - broker wiadomości (MessageBroker)
  - bazowy agent (BaseAgent)
  - orkiestrator (OrchestratorAgent)
  - wyspecjalizowane agenty gry
"""
from __future__ import annotations

import asyncio
import pytest

from src.communication.broker import MessageBroker
from src.agents.game_agents import AnalyticsAgent, ContentAgent, NarrativeAgent
from src.agents.orchestrator import OrchestratorAgent
from src.models.message import AgentMessage, AgentStatus, MessageType


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def broker() -> MessageBroker:
    return MessageBroker()


@pytest.fixture
def orchestrator(broker: MessageBroker) -> OrchestratorAgent:
    return OrchestratorAgent(broker=broker)


@pytest.fixture
def content_agent(broker: MessageBroker) -> ContentAgent:
    return ContentAgent(broker=broker)


@pytest.fixture
def narrative_agent(broker: MessageBroker) -> NarrativeAgent:
    return NarrativeAgent(broker=broker)


@pytest.fixture
def analytics_agent(broker: MessageBroker) -> AnalyticsAgent:
    return AnalyticsAgent(broker=broker)


# ─────────────────────────────────────────────────────────────────────────────
# Testy modelu wiadomości
# ─────────────────────────────────────────────────────────────────────────────


class TestAgentMessage:
    def test_to_dict_contains_required_fields(self) -> None:
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test_sender",
            payload={"key": "value"},
        )
        d = msg.to_dict()
        assert d["type"] == MessageType.TASK_REQUEST.value
        assert d["sender_id"] == "test_sender"
        assert d["payload"] == {"key": "value"}
        assert "message_id" in d
        assert "timestamp" in d

    def test_from_dict_roundtrip(self) -> None:
        original = AgentMessage(
            type=MessageType.TASK_RESULT,
            sender_id="agent_a",
            receiver_id="agent_b",
            payload={"result": 42},
            priority=5,
        )
        restored = AgentMessage.from_dict(original.to_dict())
        assert restored.type == original.type
        assert restored.sender_id == original.sender_id
        assert restored.receiver_id == original.receiver_id
        assert restored.payload == original.payload
        assert restored.priority == original.priority

    def test_unique_message_ids(self) -> None:
        msgs = [
            AgentMessage(
                type=MessageType.HEARTBEAT,
                sender_id="x",
                payload={},
            )
            for _ in range(10)
        ]
        ids = {m.message_id for m in msgs}
        assert len(ids) == 10


# ─────────────────────────────────────────────────────────────────────────────
# Testy brokera wiadomości
# ─────────────────────────────────────────────────────────────────────────────


class TestMessageBroker:
    @pytest.mark.asyncio
    async def test_direct_delivery(self, broker: MessageBroker) -> None:
        received: list[AgentMessage] = []

        async def handler(msg: AgentMessage) -> None:
            received.append(msg)

        await broker.subscribe("agent_1", handler)
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="sender",
            receiver_id="agent_1",
            payload={},
        )
        await broker.publish(msg)
        assert len(received) == 1
        assert received[0].message_id == msg.message_id

    @pytest.mark.asyncio
    async def test_broadcast_delivery(self, broker: MessageBroker) -> None:
        received_broadcast: list[AgentMessage] = []

        async def handler(msg: AgentMessage) -> None:
            received_broadcast.append(msg)

        broker.subscribe_broadcast(handler)
        msg = AgentMessage(
            type=MessageType.BROADCAST,
            sender_id="system",
            payload={"info": "broadcast"},
        )
        await broker.publish(msg)
        assert len(received_broadcast) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self, broker: MessageBroker) -> None:
        received: list[AgentMessage] = []

        async def handler(msg: AgentMessage) -> None:
            received.append(msg)

        await broker.subscribe("temp_agent", handler)
        await broker.unsubscribe("temp_agent")

        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="sender",
            receiver_id="temp_agent",
            payload={},
        )
        await broker.publish(msg)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_no_receiver_broadcasts(self, broker: MessageBroker) -> None:
        """Wiadomość bez receiver_id powinna trafić do broadcast."""
        received: list[AgentMessage] = []

        async def handler(msg: AgentMessage) -> None:
            received.append(msg)

        broker.subscribe_broadcast(handler)
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="sender",
            receiver_id=None,
            payload={},
        )
        await broker.publish(msg)
        assert len(received) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Testy wyspecjalizowanych agentów
# ─────────────────────────────────────────────────────────────────────────────


class TestContentAgent:
    @pytest.mark.asyncio
    async def test_enrich_content_returns_visual_description(
        self, content_agent: ContentAgent
    ) -> None:
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="orch",
            payload={
                "action": "enrich_content",
                "params": {},
                "context": [{"story": "Wielka przygoda rycerza"}],
            },
        )
        result = await content_agent.process_task(msg)
        assert result["status"] == "ok"
        assert "visual_description" in result["result"]
        assert "loot_table" in result["result"]

    def test_capabilities_include_content(self, content_agent: ContentAgent) -> None:
        assert "content" in content_agent.get_capabilities()


class TestNarrativeAgent:
    @pytest.mark.asyncio
    async def test_generate_story_returns_story(
        self, narrative_agent: NarrativeAgent
    ) -> None:
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="orch",
            payload={"action": "generate_story", "params": {"theme": "walka"}},
        )
        result = await narrative_agent.process_task(msg)
        assert result["status"] == "ok"
        assert isinstance(result["story"], str)
        assert len(result["story"]) > 10

    def test_capabilities_include_narrative(
        self, narrative_agent: NarrativeAgent
    ) -> None:
        assert "narrative" in narrative_agent.get_capabilities()


class TestAnalyticsAgent:
    @pytest.mark.asyncio
    async def test_analyze_returns_engagement_score(
        self, analytics_agent: AnalyticsAgent
    ) -> None:
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="orch",
            payload={
                "action": "analyze",
                "params": {
                    "session_data": {"player_level": 5, "score": 400}
                },
            },
        )
        result = await analytics_agent.process_task(msg)
        assert result["status"] == "ok"
        assert "engagement_score" in result["result"]
        assert "recommendation" in result["result"]
        assert isinstance(result["result"]["churn_risk"], bool)

    def test_capabilities_include_analytics(
        self, analytics_agent: AnalyticsAgent
    ) -> None:
        assert "analytics" in analytics_agent.get_capabilities()


# ─────────────────────────────────────────────────────────────────────────────
# Testy orkiestratora
# ─────────────────────────────────────────────────────────────────────────────


class TestOrchestratorAgent:
    def test_register_agent(self, orchestrator: OrchestratorAgent) -> None:
        orchestrator.register_agent("test_agent", ["content", "narrative"])
        assert "test_agent" in orchestrator._registry
        assert "content" in orchestrator._registry["test_agent"]["capabilities"]

    def test_select_agent_by_capability(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        orchestrator.register_agent("narrative_agent", ["narrative"])
        orchestrator.register_agent("content_agent", ["content"])
        selected = orchestrator._select_agent("narrative")
        assert selected == "narrative_agent"

    def test_select_agent_returns_none_for_unknown_capability(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        result = orchestrator._select_agent("nonexistent_capability")
        assert result is None

    def test_build_pipeline_for_generate_content(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        pipeline = orchestrator._build_pipeline("generate_content", {})
        assert len(pipeline) == 2
        capabilities = [step["capability"] for step in pipeline]
        assert "narrative" in capabilities
        assert "content" in capabilities

    def test_build_pipeline_for_analytics(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        pipeline = orchestrator._build_pipeline("analytics", {})
        assert len(pipeline) == 1
        assert pipeline[0]["capability"] == "analytics"

    def test_build_pipeline_unknown_returns_empty(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        pipeline = orchestrator._build_pipeline("unknown_task", {})
        assert pipeline == []

    def test_orchestrator_capabilities(
        self, orchestrator: OrchestratorAgent
    ) -> None:
        caps = orchestrator.get_capabilities()
        assert "orchestration" in caps
        assert "delegation" in caps
