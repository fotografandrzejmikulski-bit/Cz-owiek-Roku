"""
Testy jednostkowe klienta LLM i DynamicAgent.
"""
from __future__ import annotations

import pytest

from src.communication.llm_client import MockLlmClient, create_llm_client
from src.agents.dynamic_agent import DynamicAgent
from src.communication.broker import MessageBroker
from src.models.message import AgentMessage, MessageType


# ─────────────────────────────────────────────────────────────────────────────
# Testy klienta LLM
# ─────────────────────────────────────────────────────────────────────────────


class TestMockLlmClient:
    @pytest.mark.asyncio
    async def test_mock_returns_non_empty_string(self) -> None:
        client = MockLlmClient()
        result = await client.generate("test prompt")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_mock_includes_prompt_snippet(self) -> None:
        client = MockLlmClient()
        result = await client.generate("walka z smokiem")
        assert "walka z smokiem" in result


class TestCreateLlmClient:
    def test_returns_mock_by_default(self) -> None:
        from src.config.settings import Settings
        s = Settings(llm_backend="mock")
        client = create_llm_client(s)
        assert isinstance(client, MockLlmClient)

    def test_falls_back_to_mock_when_openai_key_missing(self) -> None:
        from src.config.settings import Settings
        s = Settings(llm_backend="openai", openai_api_key="")
        client = create_llm_client(s)
        assert isinstance(client, MockLlmClient)

    def test_falls_back_to_mock_when_gemini_key_missing(self) -> None:
        from src.config.settings import Settings
        s = Settings(llm_backend="gemini", gemini_api_key="")
        client = create_llm_client(s)
        assert isinstance(client, MockLlmClient)


# ─────────────────────────────────────────────────────────────────────────────
# Testy DynamicAgent
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def broker() -> MessageBroker:
    return MessageBroker()


class TestDynamicAgent:
    @pytest.mark.asyncio
    async def test_process_task_returns_ok(self, broker: MessageBroker) -> None:
        agent = DynamicAgent(
            agent_id="test_dynamic",
            role="tester",
            capabilities=["testing"],
            description="Agent testowy",
            broker=broker,
            llm_client=MockLlmClient(),
        )
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="orchestrator",
            payload={"action": "test", "chat_text": "przetestuj mnie"},
        )
        result = await agent.process_task(msg)
        assert result["status"] == "ok"
        assert result["agent_id"] == "test_dynamic"
        assert result["role"] == "tester"
        assert isinstance(result["result"], str)

    def test_get_capabilities_returns_given_list(self, broker: MessageBroker) -> None:
        agent = DynamicAgent(
            agent_id="cap_test",
            role="specialist",
            capabilities=["quest_design", "narrative"],
            description="Spec",
            broker=broker,
            llm_client=MockLlmClient(),
        )
        caps = agent.get_capabilities()
        assert "quest_design" in caps
        assert "narrative" in caps
