"""
Testy jednostkowe agentów specjalistycznych + MAP-Elites.

Pokrywają:
  - AgentPersona / FlowStep / AgentSOP modele
  - Wszystkie 6 klas agentów specjalistycznych
  - MapElitesScheduler (pętla ewolucyjna)
  - GridArchive (dodawanie, sample, coverage)
  - GaussianEmitter (generowanie kandydatów)
  - NoveltyEvaluator (ocena poziomu gry)
  - Endpoint GET /api/v1/specialist/agents
  - Endpoint POST /api/v1/specialist/task
  - Endpoint POST /api/v1/pcg/map-elites
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.agents.novelty_search import (
    GaussianEmitter,
    GridArchive,
    MapElitesScheduler,
    NoveltyEvaluator,
)
from src.agents.specialist_agents import (
    ALL_SPECIALIST_AGENT_CLASSES,
    BoardGameAgent,
    ComicAgent,
    GameDevAgent,
    LiteraryAgent,
    SpecialistAgent,
    SystemsEngineerAgent,
    WebDevAgent,
    create_all_specialist_agents,
)
from src.communication.broker import MessageBroker
from src.communication.llm_client import MockLlmClient
from src.models.agent_persona import (
    AgentPersona,
    AgentSOP,
    FlowStep,
    ToolAccess,
    GAMEDEV_SOP,
    LITERARY_SOP,
    SYSTEMS_SOP,
    WEBDEV_SOP,
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
# AgentPersona / FlowStep / AgentSOP
# ---------------------------------------------------------------------------

class TestAgentPersonaModels:
    def test_flow_step_to_dict(self) -> None:
        step = FlowStep(
            name="Analysis",
            description="Przeanalizuj kod.",
            on_failure="Init",
            tools=["read_file"],
        )
        d = step.to_dict()
        assert d["name"] == "Analysis"
        assert d["on_failure"] == "Init"
        assert "read_file" in d["tools"]

    def test_agent_sop_step_names(self) -> None:
        sop = SYSTEMS_SOP
        names = sop.step_names()
        assert "Analysis" in names
        assert "Generation" in names
        assert "Verification" in names

    def test_agent_sop_to_dict(self) -> None:
        d = LITERARY_SOP.to_dict()
        assert d["name"] == "NovelWriterSOP"
        assert len(d["steps"]) == 5

    def test_agent_persona_to_dict(self) -> None:
        persona = AgentPersona(
            agent_id="test_agent",
            display_name="Agent Testowy",
            domain="testing",
            goals=["Cel 1"],
            constraints=["Ogr. 1"],
            tool_access=ToolAccess.READ_ONLY,
        )
        d = persona.to_dict()
        assert d["agent_id"] == "test_agent"
        assert d["tool_access"] == "read_only"
        assert d["goals"] == ["Cel 1"]
        assert d["sop"] is None

    def test_predefined_sops_have_steps(self) -> None:
        for sop in (SYSTEMS_SOP, LITERARY_SOP, GAMEDEV_SOP, WEBDEV_SOP):
            assert len(sop.steps) >= 3

    def test_tool_access_sandboxed(self) -> None:
        assert ToolAccess.SANDBOXED.value == "sandboxed"

    def test_tool_access_full_shell(self) -> None:
        assert ToolAccess.FULL_SHELL.value == "full_shell"


# ---------------------------------------------------------------------------
# Fabryka agentów specjalistycznych
# ---------------------------------------------------------------------------

class TestSpecialistAgentFactory:
    def test_creates_all_agents(self, broker: MessageBroker) -> None:
        agents = create_all_specialist_agents(broker=broker)
        assert len(agents) == len(ALL_SPECIALIST_AGENT_CLASSES)

    def test_all_agents_have_unique_ids(self, broker: MessageBroker) -> None:
        agents = create_all_specialist_agents(broker=broker)
        ids = [a.agent_id for a in agents]
        assert len(ids) == len(set(ids))

    def test_all_agents_are_specialist_subclass(self, broker: MessageBroker) -> None:
        for cls in ALL_SPECIALIST_AGENT_CLASSES:
            agent = cls(broker=broker)
            assert isinstance(agent, SpecialistAgent)


# ---------------------------------------------------------------------------
# Persony poszczególnych agentów
# ---------------------------------------------------------------------------

class TestSpecialistAgentPersonas:
    def test_systems_engineer_domain(self, broker: MessageBroker) -> None:
        a = SystemsEngineerAgent(broker=broker)
        assert a.persona.domain == "systems_engineering"
        assert a.persona.tool_access == ToolAccess.SANDBOXED

    def test_gamedev_sop_has_bugsfix_step(self, broker: MessageBroker) -> None:
        a = GameDevAgent(broker=broker)
        assert "BugFixing" in a.persona.sop.step_names()

    def test_literary_agent_context_window(self, broker: MessageBroker) -> None:
        a = LiteraryAgent(broker=broker)
        assert a.persona.context_window == 200_000

    def test_comic_agent_capabilities(self, broker: MessageBroker) -> None:
        a = ComicAgent(broker=broker)
        caps = a.get_capabilities()
        assert "specialist" in caps
        assert "comic_creation" in caps

    def test_boardgame_agent_has_evolution_step(self, broker: MessageBroker) -> None:
        a = BoardGameAgent(broker=broker)
        assert "Evolution" in a.persona.sop.step_names()

    def test_webdev_agent_has_qa_step(self, broker: MessageBroker) -> None:
        a = WebDevAgent(broker=broker)
        assert "QA" in a.persona.sop.step_names()

    def test_all_agents_have_goals_and_constraints(self, broker: MessageBroker) -> None:
        for cls in ALL_SPECIALIST_AGENT_CLASSES:
            a = cls(broker=broker)
            assert len(a.persona.goals) >= 1
            assert len(a.persona.constraints) >= 1

    def test_get_persona_returns_dict(self, broker: MessageBroker) -> None:
        a = SystemsEngineerAgent(broker=broker)
        d = a.get_persona()
        assert d["agent_id"] == "systems_engineer"
        assert "goals" in d
        assert "sop" in d


# ---------------------------------------------------------------------------
# Przetwarzanie zadania – agenty specjalistyczne
# ---------------------------------------------------------------------------

class TestSpecialistAgentProcessTask:
    @pytest.mark.asyncio
    async def test_process_task_returns_response(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = SystemsEngineerAgent(broker=broker, llm_client=mock_llm)
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="dev",
            receiver_id=agent.agent_id,
            payload={
                "task":  "Migruj sterownik USB z C na Rust.",
                "step":  "Analysis",
            },
        )
        result = await agent.process_task(message)
        assert result["status"] == "ok"
        assert result["agent_id"] == "systems_engineer"
        assert "sop_steps" in result
        assert "Analysis" in result["sop_steps"]

    @pytest.mark.asyncio
    async def test_gamedev_agent_with_context(
        self, broker: MessageBroker, mock_llm: MockLlmClient
    ) -> None:
        agent = GameDevAgent(broker=broker, llm_client=mock_llm)
        message = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id="dev",
            receiver_id=agent.agent_id,
            payload={
                "task": "Stwórz klasę AExplosiveBarrel dla UE5.",
                "context": [{"role": "user", "content": "Używamy C++."}],
            },
        )
        result = await agent.process_task(message)
        assert result["status"] == "ok"
        assert result["domain"] == "gamedev"


# ---------------------------------------------------------------------------
# GridArchive
# ---------------------------------------------------------------------------

class TestGridArchive:
    def test_add_solution_fills_cell(self) -> None:
        archive = GridArchive(solution_dim=4, dims=[10, 10], ranges=[(0, 1), (0, 1)])
        updated = archive.add([0.1, 0.2, 0.3, 0.4], 0.8, (0.1, 0.2))
        assert updated is True
        assert archive.size == 1

    def test_better_solution_replaces_worse(self) -> None:
        archive = GridArchive(solution_dim=2, dims=[5, 5], ranges=[(0, 1), (0, 1)])
        archive.add([0.5, 0.5], 0.6, (0.5, 0.5))
        updated = archive.add([0.5, 0.6], 0.9, (0.5, 0.5))  # ta sama komórka
        assert updated is True
        assert archive.best_elite().objective == 0.9

    def test_worse_solution_rejected(self) -> None:
        archive = GridArchive(solution_dim=2, dims=[5, 5], ranges=[(0, 1), (0, 1)])
        archive.add([0.5, 0.5], 0.9, (0.5, 0.5))
        updated = archive.add([0.5, 0.6], 0.3, (0.5, 0.5))
        assert updated is False

    def test_coverage_calculation(self) -> None:
        archive = GridArchive(solution_dim=2, dims=[4, 4], ranges=[(0, 1), (0, 1)])
        assert archive.coverage() == 0.0
        archive.add([0.1], 0.5, (0.1, 0.1))
        assert archive.coverage() > 0.0

    def test_sample_elite_none_when_empty(self) -> None:
        archive = GridArchive(solution_dim=2, dims=[5, 5], ranges=[(0, 1), (0, 1)])
        assert archive.sample_elite() is None

    def test_to_dict_keys(self) -> None:
        archive = GridArchive(solution_dim=5, dims=[10, 10], ranges=[(0, 1), (0, 1)])
        d = archive.to_dict()
        for key in ("solution_dim", "dims", "ranges", "size", "coverage"):
            assert key in d

    def test_clamping_out_of_range_behavior(self) -> None:
        archive = GridArchive(solution_dim=2, dims=[10, 10], ranges=[(0, 1), (0, 1)])
        # wartości poza zakresem powinny być zaciśnięte do granicznych komórek
        archive.add([0.5, 0.5], 1.0, (2.0, -1.0))  # nie powinno rzucać błędu
        assert archive.size == 1


# ---------------------------------------------------------------------------
# GaussianEmitter
# ---------------------------------------------------------------------------

class TestGaussianEmitter:
    def test_generates_correct_batch_size(self) -> None:
        archive = GridArchive(solution_dim=4, dims=[10, 10], ranges=[(0, 1), (0, 1)])
        emitter = GaussianEmitter(archive, sigma=0.1, batch_size=16)
        solutions = emitter.ask()
        assert len(solutions) == 16

    def test_solutions_are_clamped_to_unit_range(self) -> None:
        archive = GridArchive(solution_dim=4, dims=[10, 10], ranges=[(0, 1), (0, 1)])
        emitter = GaussianEmitter(archive, sigma=0.5, batch_size=50)
        for sol in emitter.ask():
            for val in sol:
                assert 0.0 <= val <= 1.0

    def test_mutates_around_elite(self) -> None:
        archive = GridArchive(solution_dim=2, dims=[10, 10], ranges=[(0, 1), (0, 1)])
        archive.add([0.9, 0.9], 1.0, (0.9, 0.9))
        emitter = GaussianEmitter(archive, sigma=0.001, batch_size=10)
        solutions = emitter.ask()
        # Z bardzo małą sigma rozwiązania powinny być blisko [0.9, 0.9]
        for sol in solutions:
            assert abs(sol[0] - 0.9) < 0.1


# ---------------------------------------------------------------------------
# MapElitesScheduler
# ---------------------------------------------------------------------------

class TestMapElitesScheduler:
    def test_tell_requires_matching_length(self) -> None:
        archive = GridArchive(solution_dim=2, dims=[5, 5], ranges=[(0, 1), (0, 1)])
        emitter = GaussianEmitter(archive, batch_size=4)
        scheduler = MapElitesScheduler(archive, [emitter])
        scheduler.ask()  # generuje 4 rozwiązania
        with pytest.raises(ValueError):
            scheduler.tell([0.5, 0.5], [(0.1, 0.1), (0.2, 0.2)])  # tylko 2 wyniki

    def test_run_fills_archive(self) -> None:
        archive = GridArchive(solution_dim=4, dims=[10, 10], ranges=[(0, 1), (0, 1)])
        emitter = GaussianEmitter(archive, batch_size=32)
        scheduler = MapElitesScheduler(archive, [emitter])
        scheduler.run(NoveltyEvaluator.evaluate, iterations=10)
        assert archive.size > 0

    def test_stats_after_run(self) -> None:
        archive = GridArchive(solution_dim=4, dims=[5, 5], ranges=[(0, 1), (0, 1)])
        emitter = GaussianEmitter(archive, batch_size=16)
        scheduler = MapElitesScheduler(archive, [emitter])
        scheduler.run(NoveltyEvaluator.evaluate, iterations=5)
        stats = scheduler.stats()
        assert stats["iteration"] == 5
        assert stats["coverage"] >= 0.0


# ---------------------------------------------------------------------------
# NoveltyEvaluator
# ---------------------------------------------------------------------------

class TestNoveltyEvaluator:
    def test_evaluate_returns_correct_lengths(self) -> None:
        solutions = [[0.5] * 4, [0.3] * 4, [0.8] * 4]
        objectives, behaviors = NoveltyEvaluator.evaluate(solutions)
        assert len(objectives) == 3
        assert len(behaviors) == 3

    def test_balanced_solution_scores_high(self) -> None:
        solutions = [[0.5, 0.5, 0.5, 0.5]]
        objectives, _ = NoveltyEvaluator.evaluate(solutions)
        # balanced (all 0.5) → minimalna kara → wysokie fitness
        assert objectives[0] > 0.85

    def test_extreme_solution_scores_low(self) -> None:
        solutions = [[1.0, 1.0, 1.0, 1.0]]
        objectives, _ = NoveltyEvaluator.evaluate(solutions)
        # skrajna wartość → duża kara
        assert objectives[0] < 0.6

    def test_behavior_coordinates_are_bounded(self) -> None:
        solutions = [[random_val / 10 for random_val in range(10)]]
        _, behaviors = NoveltyEvaluator.evaluate(solutions)
        for b in behaviors:
            for coord in b:
                assert 0.0 <= coord <= 1.0


# ---------------------------------------------------------------------------
# REST API – specialist endpoints
# ---------------------------------------------------------------------------

class TestSpecialistEndpoints:
    def test_list_specialist_agents(self, api_client) -> None:
        response = api_client.get("/api/v1/specialist/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == len(ALL_SPECIALIST_AGENT_CLASSES)

    def test_specialist_agents_have_persona_fields(self, api_client) -> None:
        response = api_client.get("/api/v1/specialist/agents")
        for entry in response.json():
            assert "agent_id" in entry
            assert "domain" in entry
            assert "goals" in entry
            assert "sop" in entry

    def test_specialist_task_systems_engineer(self, api_client) -> None:
        response = api_client.post("/api/v1/specialist/task", json={
            "client_id": "dev",
            "agent_id":  "systems_engineer",
            "task":      "Napisz moduł zarządzania pamięcią w Rust.",
            "step":      "Generation",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["domain"] == "systems_engineering"
        assert "Generation" in data["sop_steps"] or len(data["sop_steps"]) > 0

    def test_specialist_task_unknown_agent_404(self, api_client) -> None:
        response = api_client.post("/api/v1/specialist/task", json={
            "client_id": "dev",
            "agent_id":  "nie_istnieje",
            "task":      "Zadanie.",
        })
        assert response.status_code == 404

    def test_map_elites_endpoint(self, api_client) -> None:
        response = api_client.post("/api/v1/pcg/map-elites", json={
            "solution_dim": 4,
            "grid_dims": [5, 5],
            "grid_ranges": [[0.0, 1.0], [0.0, 1.0]],
            "iterations": 20,
            "sigma": 0.1,
            "batch_size": 16,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["iterations"] == 20
        assert data["archive_size"] > 0
        assert 0.0 <= data["coverage"] <= 1.0

    def test_map_elites_best_objective_is_float(self, api_client) -> None:
        response = api_client.post("/api/v1/pcg/map-elites", json={
            "solution_dim": 4,
            "grid_dims": [5, 5],
            "grid_ranges": [[0.0, 1.0], [0.0, 1.0]],
            "iterations": 10,
        })
        data = response.json()
        assert isinstance(data["best_objective"], float)
        assert 0.0 <= data["best_objective"] <= 1.0
