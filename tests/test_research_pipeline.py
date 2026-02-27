"""
Testy jednostkowe potoku Deep Research.

Pokrywają:
  - MockSearchClient
  - DeepResearchOrchestrator (fazy 1-4)
  - ResearchState (model danych)
"""
from __future__ import annotations

import pytest

from src.communication.broker import MessageBroker
from src.communication.llm_client import MockLlmClient
from src.communication.search_client import MockSearchClient, create_search_client
from src.agents.research_agents import DeepResearchOrchestrator
from src.models.message import AgentMessage, MessageType
from src.models.research_state import ResearchState, ResearchStatus


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def broker() -> MessageBroker:
    return MessageBroker()


@pytest.fixture
def research_agent(broker: MessageBroker) -> DeepResearchOrchestrator:
    return DeepResearchOrchestrator(
        broker=broker,
        llm_planner=MockLlmClient(),
        llm_worker=MockLlmClient(),
        search_client=MockSearchClient(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# MockSearchClient
# ─────────────────────────────────────────────────────────────────────────────

class TestMockSearchClient:
    @pytest.mark.asyncio
    async def test_returns_results(self) -> None:
        client = MockSearchClient()
        results = await client.search("trendy w AI 2025", max_results=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_result_has_required_fields(self) -> None:
        client = MockSearchClient()
        results = await client.search("testowe zapytanie")
        r = results[0]
        assert r.url.startswith("https://")
        assert len(r.title) > 0
        assert len(r.content) > 0
        assert 0.0 <= r.score <= 1.0

    def test_create_returns_mock_without_key(self) -> None:
        from src.config.settings import Settings
        s = Settings(tavily_api_key="")
        client = create_search_client(s)
        assert isinstance(client, MockSearchClient)


# ─────────────────────────────────────────────────────────────────────────────
# ResearchState
# ─────────────────────────────────────────────────────────────────────────────

class TestResearchState:
    def test_initial_status_is_pending(self) -> None:
        state = ResearchState(query="test")
        assert state.status == ResearchStatus.PENDING

    def test_to_dict_contains_all_keys(self) -> None:
        state = ResearchState(query="co to jest AI?", quality_score=80, iteration=2)
        d = state.to_dict()
        assert d["query"] == "co to jest AI?"
        assert d["quality_score"] == 80
        assert d["iteration"] == 2
        assert "status" in d
        assert "sub_questions" in d
        assert "final_report" in d


# ─────────────────────────────────────────────────────────────────────────────
# DeepResearchOrchestrator – fazy potoku
# ─────────────────────────────────────────────────────────────────────────────

class TestDeepResearchOrchestrator:
    def test_capabilities(self, research_agent: DeepResearchOrchestrator) -> None:
        caps = research_agent.get_capabilities()
        assert "deep_research" in caps
        assert "report_synthesis" in caps

    @pytest.mark.asyncio
    async def test_plan_returns_sub_questions(
        self, research_agent: DeepResearchOrchestrator
    ) -> None:
        state = ResearchState(query="Jak dzialaja agenty AI?")
        plan = await research_agent._plan(state)
        assert plan.main_query == "Jak dzialaja agenty AI?"
        assert len(plan.sub_questions) >= 1
        assert all(isinstance(q, str) for q in plan.sub_questions)

    @pytest.mark.asyncio
    async def test_research_parallel_returns_findings(
        self, research_agent: DeepResearchOrchestrator
    ) -> None:
        from src.models.research_state import ResearchPlan
        state = ResearchState(query="test")
        state.plan = ResearchPlan(
            main_query="test",
            sub_questions=["pytanie 1", "pytanie 2"],
        )
        findings = await research_agent._research_parallel(state)
        assert len(findings) == 2
        for f in findings:
            assert isinstance(f.summary, str)
            assert len(f.summary) > 0

    @pytest.mark.asyncio
    async def test_critique_returns_score_and_feedback(
        self, research_agent: DeepResearchOrchestrator
    ) -> None:
        from src.models.research_state import ResearchFinding, ResearchPlan
        state = ResearchState(query="test")
        state.plan = ResearchPlan(main_query="test", sub_questions=["q1"])
        state.findings = [
            ResearchFinding(sub_question="q1", summary="Wyniki badan.")
        ]
        result = await research_agent._critique(state)
        assert "score" in result
        assert "feedback" in result
        assert 0 <= result["score"] <= 100
        assert isinstance(result["feedback"], list)

    @pytest.mark.asyncio
    async def test_full_pipeline_returns_report(
        self, research_agent: DeepResearchOrchestrator
    ) -> None:
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test_client",
            payload={
                "query": "Jakie sa trendy w grach AAA w 2025?",
                "max_iterations": 1,
                "reflection_threshold": 0,  # Accept any quality – fast test
            },
        )
        result = await research_agent.process_task(msg)
        assert result["status"] == "done"
        assert isinstance(result["final_report"], str)
        assert len(result["final_report"]) > 10
        assert "query" in result
        assert "quality_score" in result

    @pytest.mark.asyncio
    async def test_reflection_loop_stops_at_threshold(
        self, research_agent: DeepResearchOrchestrator
    ) -> None:
        """Petla refleksji zatrzymuje sie gdy quality_score >= threshold."""
        msg = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="test",
            payload={
                "query": "test refleksji",
                "max_iterations": 3,
                "reflection_threshold": 0,  # zawsze zatrzymuje po pierwszej iteracji
            },
        )
        result = await research_agent.process_task(msg)
        # Przy threshold=0 powinno wykonac tylko 1 iteracje
        assert result["iteration"] == 1
