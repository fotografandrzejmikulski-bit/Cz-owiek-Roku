"""
Routery FastAPI dla zasobów REST API.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.models.message import AgentMessage, AgentStatus, MessageType

# ---------------------------------------------------------------------------
# Schematy Pydantic (walidacja wejścia/wyjścia)
# ---------------------------------------------------------------------------


class TaskRequest(BaseModel):
    """Żądanie zadania od klienta (Android/Windows)."""
    client_id: str
    task_type: str
    payload: dict[str, Any] = {}


class TaskResponse(BaseModel):
    """Odpowiedź na zlecone zadanie."""
    task_id: str
    status: str
    result: dict[str, Any] | None = None


class AgentInfo(BaseModel):
    """Informacje o agencie w systemie."""
    agent_id: str
    capabilities: list[str]
    status: str


class ChatMessageRequest(BaseModel):
    """Wiadomość czatu od użytkownika – tekst naturalny."""
    client_id: str
    text: str = Field(..., min_length=1, max_length=2000)


class ChatMessageResponse(BaseModel):
    """Potwierdzenie przyjęcia wiadomości czatu."""
    chat_id: str
    status: str
    echo: str


class AgentBuilderRequest(BaseModel):
    """Żądanie zbudowania nowego agenta w czasie wykonania."""
    name: str = Field(..., min_length=2, max_length=64,
                      pattern=r"^[a-z0-9_]+$",
                      description="Unikalny identyfikator agenta (małe litery, cyfry, _)")
    role: str = Field(..., min_length=2, max_length=64,
                      description="Krótka nazwa roli (np. quest_designer)")
    capabilities: list[str] = Field(..., min_length=1,
                                    description="Lista możliwości agenta")
    description: str = Field(
        default="",
        max_length=500,
        description="Opis działania agenta – używany jako kontekst w LLM",
    )


class AgentBuilderResponse(BaseModel):
    """Odpowiedź po zbudowaniu nowego agenta."""
    agent_id: str
    status: str
    capabilities: list[str]


# ---------------------------------------------------------------------------
# Pomocnicza funkcja: wykrywanie intencji z tekstu
# ---------------------------------------------------------------------------

def _infer_task_type(text: str) -> tuple[str, dict[str, Any]]:
    """
    Wywnioskuj typ zadania i dodatkowe parametry z treści wiadomości czatu.
    Używa prostego dopasowania słów kluczowych (w produkcji: LLM intent parser).
    """
    lower = text.lower()
    if any(k in lower for k in ("analiz", "statystyki", "zachowania", "analytics", "analityk")):
        return "analytics", {}
    if any(k in lower for k in ("badaj", "zbadaj", "raport", "research", "przeanalizuj", "przebadaj")):
        return "deep_research", {"query": text}
    # Domyślnie: generowanie treści (narracja + wzbogacanie)
    return "generate_content", {"theme": text}


# ---------------------------------------------------------------------------
# Router: zadania
# ---------------------------------------------------------------------------
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])


@tasks_router.post("/", response_model=TaskResponse)
async def submit_task(task: TaskRequest, request: Request) -> TaskResponse:
    """
    Przyjmij zadanie od klienta i przekaż orkiestratorowi.
    Wynik zostanie wysłany przez WebSocket (async push).
    """
    broker = request.app.state.broker

    message = AgentMessage(
        type=MessageType.TASK_REQUEST,
        sender_id=task.client_id,
        receiver_id="orchestrator",
        payload={"task_type": task.task_type, **task.payload},
    )

    # Publikuj asynchronicznie – nie blokuj odpowiedzi HTTP
    asyncio.create_task(broker.publish(message))

    return TaskResponse(
        task_id=message.message_id,
        status="accepted",
    )


# ---------------------------------------------------------------------------
# Router: agenty
# ---------------------------------------------------------------------------
agents_router = APIRouter(prefix="/agents", tags=["agents"])


@agents_router.get("/", response_model=list[AgentInfo])
async def list_agents(request: Request) -> list[AgentInfo]:
    """Zwróć listę zarejestrowanych agentów i ich status."""
    orchestrator = request.app.state.orchestrator
    agents = []
    for agent_id, meta in orchestrator._registry.items():
        agents.append(
            AgentInfo(
                agent_id=agent_id,
                capabilities=meta.get("capabilities", []),
                status=str(meta.get("status", AgentStatus.IDLE)),
            )
        )
    return agents


@agents_router.get("/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str, request: Request) -> AgentInfo:
    """Zwróć szczegóły konkretnego agenta."""
    orchestrator = request.app.state.orchestrator
    meta = orchestrator._registry.get(agent_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' nie znaleziony.")
    return AgentInfo(
        agent_id=agent_id,
        capabilities=meta.get("capabilities", []),
        status=str(meta.get("status", AgentStatus.IDLE)),
    )


@agents_router.post("/", response_model=AgentBuilderResponse, status_code=201)
async def build_agent(
    spec: AgentBuilderRequest, request: Request
) -> AgentBuilderResponse:
    """
    **Budowniczy Agentów** – zarejestruj nowego agenta w czasie wykonania.

    Tworzy DynamicAgent z podanymi możliwościami i rejestruje go w orkiestratorze.
    Agent jest natychmiast dostępny do przyjmowania zadań przez czat lub REST.

    Przykład:
    ```json
    {
        "name": "quest_agent",
        "role": "projektant_questów",
        "capabilities": ["quest_design", "narrative"],
        "description": "Tworzy zadania poboczne dla gracza w oparciu o fabułę"
    }
    ```
    """
    orchestrator = request.app.state.orchestrator
    broker = request.app.state.broker

    if spec.name in orchestrator._registry:
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{spec.name}' już istnieje w rejestrze.",
        )

    # Importuj tutaj, by uniknąć cyklicznych zależności modułów
    from src.agents.dynamic_agent import DynamicAgent

    agent = DynamicAgent(
        agent_id=spec.name,
        role=spec.role,
        capabilities=spec.capabilities,
        description=spec.description,
        broker=broker,
    )
    orchestrator.register_agent(spec.name, spec.capabilities)
    # Uruchom agenta jako zadanie asyncio (nie blokuje odpowiedzi HTTP)
    import asyncio
    asyncio.create_task(agent.start())

    return AgentBuilderResponse(
        agent_id=spec.name,
        status="uruchomiony",
        capabilities=spec.capabilities,
    )


# ---------------------------------------------------------------------------
# Router: czat z agentami
# ---------------------------------------------------------------------------
chat_router = APIRouter(prefix="/chat", tags=["chat"])


@chat_router.post("/", response_model=ChatMessageResponse)
async def send_chat_message(
    chat: ChatMessageRequest, request: Request
) -> ChatMessageResponse:
    """
    Wyślij wiadomość do agentów poprzez interfejs czatu.

    Tekst jest analizowany pod kątem intencji, a następnie odpowiednie zadanie
    jest przekazywane do orkiestratora. Odpowiedź agenta przyjedzie przez
    WebSocket (/ws) jako zdarzenie ``task_result``.

    Przykłady:
    - ``"wygeneruj treść o walce"`` → zadanie ``generate_content``
    - ``"analiza zachowań gracza"`` → zadanie ``analytics``
    """
    broker = request.app.state.broker
    task_type, extra_payload = _infer_task_type(chat.text)

    message = AgentMessage(
        type=MessageType.TASK_REQUEST,
        sender_id=chat.client_id,
        receiver_id="orchestrator",
        payload={
            "task_type": task_type,
            "chat_text": chat.text,
            **extra_payload,
        },
    )

    asyncio.create_task(broker.publish(message))

    return ChatMessageResponse(
        chat_id=message.message_id,
        status="accepted",
        echo=chat.text,
    )


# ---------------------------------------------------------------------------
# Schematy: Deep Research
# ---------------------------------------------------------------------------

class ResearchRequest(BaseModel):
    """Żądanie uruchomienia procesu Deep Research."""
    client_id: str
    query: str = Field(..., min_length=5, max_length=2000,
                       description="Pytanie badawcze w języku naturalnym")
    max_iterations: int = Field(
        default=3, ge=1, le=5,
        description="Maks. liczba iteracji pętli refleksji Critic→Planner",
    )
    reflection_threshold: int = Field(
        default=75, ge=0, le=100,
        description="Minimalny wynik jakości (0-100) do zakończenia pętli",
    )


class ResearchResponse(BaseModel):
    """Odpowiedź na uruchomienie badania – wynik przyjedzie przez WebSocket."""
    research_id: str
    status: str
    query: str


class ResearchProgressEvent(BaseModel):
    """Zdarzenie postępu badania wysyłane przez WebSocket."""
    research_id: str
    status: str
    query: str
    iteration: int = 0
    quality_score: int = 0
    sub_questions: list[str] = []
    final_report: str = ""
    feedback: list[str] = []


# ---------------------------------------------------------------------------
# Router: Deep Research
# ---------------------------------------------------------------------------
research_router = APIRouter(prefix="/research", tags=["research"])


@research_router.post("/", response_model=ResearchResponse)
async def start_research(
    research: ResearchRequest, request: Request
) -> ResearchResponse:
    """
    **Deep Research** – uruchom wieloetapowy proces badawczy.

    Potok: Planner → Researcher(fan-out) → Critic(refleksja) → Writer.
    Postęp i wynik końcowy dotrą przez WebSocket jako zdarzenia
    ``research_progress``.

    Przykłady zapytań:
    - ``"Analiza trendów w AI w 2025 roku"``
    - ``"Jakie są najlepsze strategie monetyzacji gier mobilnych?"``
    - ``"Porównaj frameworki do budowy agentów AI"``
    """
    broker = request.app.state.broker

    message = AgentMessage(
        type=MessageType.TASK_REQUEST,
        sender_id=research.client_id,
        receiver_id="deep_research_orchestrator",
        payload={
            "query": research.query,
            "max_iterations": research.max_iterations,
            "reflection_threshold": research.reflection_threshold,
        },
    )

    asyncio.create_task(broker.publish(message))

    return ResearchResponse(
        research_id=message.message_id,
        status="accepted",
        query=research.query,
    )


@research_router.get("/status", tags=["research"])
async def research_capabilities() -> dict[str, Any]:
    """Zwróć informacje o możliwościach systemu Deep Research."""
    return {
        "pipeline": ["planner", "researcher_fan_out", "critic_reflector", "writer"],
        "max_parallel_researchers": 5,
        "supported_backends": ["mock", "openai", "gemini"],
        "search_providers": ["mock", "tavily"],
        "reflection_loop": True,
    }


# ---------------------------------------------------------------------------
# Router: Edukacja (AAK – Cyfrowa Agora Wiedzy)
# ---------------------------------------------------------------------------

class EduSessionRequest(BaseModel):
    """Pytanie ucznia do agenta dydaktycznego."""
    client_id: str
    agent_id: str = Field(
        ...,
        description="Identyfikator agenta (np. 'mickiewiczai', 'eulerredu')",
    )
    query: str = Field(..., min_length=1, max_length=2000)
    level: str = Field(
        default="nieznany",
        description="Poziom realizacji: 'podstawowy' lub 'rozszerzony'",
    )
    history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Historia rozmowy [{role, content}, ...]",
    )


class EduSessionResponse(BaseModel):
    """Odpowiedź agenta dydaktycznego."""
    session_id: str
    agent_id: str
    subject: str
    level: str
    response: str
    status: str


edu_router = APIRouter(prefix="/edu", tags=["edu"])


@edu_router.get("/agents", tags=["edu"])
async def list_edu_agents(request: Request) -> list[dict[str, str]]:
    """Zwróć listę dostępnych agentów dydaktycznych (AAK)."""
    edu_agents = getattr(request.app.state, "edu_agents", {})
    return [
        {"agent_id": a.agent_id, "subject": a.subject_name, "domain": a.subject_domain.value}
        for a in edu_agents.values()
    ]


@edu_router.post("/session", response_model=EduSessionResponse)
async def edu_session(req: EduSessionRequest, request: Request) -> EduSessionResponse:
    """
    Wyślij pytanie do agenta dydaktycznego.

    Pytanie jest przetwarzane synchronicznie (krótkie odpowiedzi) lub
    asynchronicznie z wynikiem przez WebSocket (długie odpowiedzi).
    """
    edu_agents = getattr(request.app.state, "edu_agents", {})
    agent = edu_agents.get(req.agent_id)

    if agent is None:
        available = list(edu_agents.keys())
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Agent '{req.agent_id}' nie istnieje.",
                "available": available,
            },
        )

    from src.models.message import AgentMessage, MessageType
    message = AgentMessage(
        type=MessageType.TASK_REQUEST,
        sender_id=req.client_id,
        receiver_id=agent.agent_id,
        payload={
            "query":   req.query,
            "level":   req.level,
            "history": req.history,
        },
    )

    result = await agent.process_task(message)

    return EduSessionResponse(
        session_id=result.get("session", {}).get("session_id", message.message_id),
        agent_id=result.get("agent_id", req.agent_id),
        subject=result.get("subject", ""),
        level=result.get("level", req.level),
        response=result.get("response", ""),
        status=result.get("status", "ok"),
    )


# ---------------------------------------------------------------------------
# Router: Agenty Specjalistyczne (Inżynieria / GameDev / Pisarstwo / Web)
# ---------------------------------------------------------------------------

class SpecialistTaskRequest(BaseModel):
    """Zadanie dla agenta specjalistycznego."""
    client_id: str
    agent_id: str = Field(
        ...,
        description="np. 'systems_engineer', 'gamedev_agent', 'literary_agent'",
    )
    task: str = Field(..., min_length=1, max_length=4000)
    step: str = Field(
        default="",
        description="Opcjonalny krok SOP (np. 'Analysis', 'Generation')",
    )
    context: list[dict[str, str]] = Field(default_factory=list)


class SpecialistTaskResponse(BaseModel):
    """Odpowiedź agenta specjalistycznego."""
    task_id: str
    agent_id: str
    domain: str
    display_name: str
    response: str
    sop_steps: list[str]
    status: str


specialist_router = APIRouter(prefix="/specialist", tags=["specialist"])


@specialist_router.get("/agents", tags=["specialist"])
async def list_specialist_agents(request: Request) -> list[dict[str, Any]]:
    """Zwróć listę dostępnych agentów specjalistycznych z ich Personami."""
    specialist_agents = getattr(request.app.state, "specialist_agents", {})
    return [a.get_persona() for a in specialist_agents.values()]


@specialist_router.post("/task", response_model=SpecialistTaskResponse)
async def specialist_task(req: SpecialistTaskRequest, request: Request) -> SpecialistTaskResponse:
    """Wyślij zadanie do agenta specjalistycznego."""
    specialist_agents = getattr(request.app.state, "specialist_agents", {})
    agent = specialist_agents.get(req.agent_id)

    if agent is None:
        available = list(specialist_agents.keys())
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Agent specjalistyczny '{req.agent_id}' nie istnieje.",
                "available": available,
            },
        )

    from src.models.message import AgentMessage, MessageType
    message = AgentMessage(
        type=MessageType.TASK_REQUEST,
        sender_id=req.client_id,
        receiver_id=agent.agent_id,
        payload={
            "task":    req.task,
            "step":    req.step,
            "context": req.context,
        },
    )

    result = await agent.process_task(message)

    return SpecialistTaskResponse(
        task_id=message.message_id,
        agent_id=result.get("agent_id", req.agent_id),
        domain=result.get("domain", ""),
        display_name=result.get("display_name", ""),
        response=result.get("response", ""),
        sop_steps=result.get("sop_steps", []),
        status=result.get("status", "ok"),
    )


# ---------------------------------------------------------------------------
# Router: MAP-Elites / Novelty Search (PCG – Procedural Content Generation)
# ---------------------------------------------------------------------------

class MapElitesRequest(BaseModel):
    """Parametry uruchomienia algorytmu MAP-Elites."""
    solution_dim: int = Field(default=10, ge=2, le=50)
    grid_dims: list[int] = Field(default=[20, 20])
    grid_ranges: list[list[float]] = Field(default=[[0.0, 1.0], [0.0, 1.0]])
    iterations: int = Field(default=100, ge=10, le=1000)
    sigma: float = Field(default=0.1, ge=0.01, le=1.0)
    batch_size: int = Field(default=32, ge=8, le=128)


class MapElitesResponse(BaseModel):
    """Wyniki algorytmu MAP-Elites."""
    run_id: str
    iterations: int
    archive_size: int
    coverage: float
    best_objective: float | None
    archive_info: dict[str, Any]
    status: str


pcg_router = APIRouter(prefix="/pcg", tags=["pcg"])


@pcg_router.post("/map-elites", response_model=MapElitesResponse)
async def run_map_elites(req: MapElitesRequest) -> MapElitesResponse:
    """
    Uruchom algorytm MAP-Elites do proceduralnej generacji treści.

    Używa wbudowanego NoveltyEvaluator (ocena 'grywalności' poziomu gry).
    W produkcji: zamień ewaluator na wywołanie LLM lub symulatora gry.
    """
    from src.agents.novelty_search import (
        GridArchive, GaussianEmitter, MapElitesScheduler, NoveltyEvaluator,
    )
    import uuid

    run_id = str(uuid.uuid4())

    ranges_typed = [(r[0], r[1]) for r in req.grid_ranges]

    archive = GridArchive(
        solution_dim=req.solution_dim,
        dims=req.grid_dims,
        ranges=ranges_typed,
    )
    emitters = [GaussianEmitter(archive, sigma=req.sigma, batch_size=req.batch_size)]
    scheduler = MapElitesScheduler(archive, emitters)

    scheduler.run(
        evaluator=NoveltyEvaluator.evaluate,
        iterations=req.iterations,
    )

    stats = scheduler.stats()
    best = archive.best_elite()

    return MapElitesResponse(
        run_id=run_id,
        iterations=stats["iteration"],
        archive_size=stats["archive_size"],
        coverage=stats["coverage"],
        best_objective=best.objective if best else None,
        archive_info=archive.to_dict(),
        status="completed",
    )


# ---------------------------------------------------------------------------
# Router: Youth Agents (Alpha/Z ecosystem)
# ---------------------------------------------------------------------------

class YouthSessionRequest(BaseModel):
    """Zapytanie do agenta dla Generacji Alpha/Z."""
    client_id: str
    agent_id: str = Field(
        ...,
        description="np. 'skarbnikagent', 'biooptymizer', 'stratgesportowy'",
    )
    query: str = Field(..., min_length=1, max_length=2000)
    age_group: str = Field(
        default="teen",
        description="'preteen' (10-12), 'teen' (13-17), 'young_adult' (18-24)",
    )
    history: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class YouthSessionResponse(BaseModel):
    """Odpowiedź agenta youth."""
    session_id: str
    agent_id: str
    display_name: str
    age_group: str
    safety_level: str
    response: str
    status: str


youth_router = APIRouter(prefix="/youth", tags=["youth"])


@youth_router.get("/agents", tags=["youth"])
async def list_youth_agents(request: Request) -> list[dict[str, str]]:
    """Zwróć listę dostępnych agentów dla Generacji Alpha/Z."""
    youth_agents = getattr(request.app.state, "youth_agents", {})
    return [a.get_info() for a in youth_agents.values()]


@youth_router.post("/session", response_model=YouthSessionResponse)
async def youth_session(req: YouthSessionRequest, request: Request) -> YouthSessionResponse:
    """Wyślij zapytanie do agenta dla Generacji Alpha/Z."""
    youth_agents = getattr(request.app.state, "youth_agents", {})
    agent = youth_agents.get(req.agent_id)

    if agent is None:
        available = list(youth_agents.keys())
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Agent youth '{req.agent_id}' nie istnieje.",
                "available": available,
            },
        )

    from src.models.message import AgentMessage, MessageType
    message = AgentMessage(
        type=MessageType.TASK_REQUEST,
        sender_id=req.client_id,
        receiver_id=agent.agent_id,
        payload={
            "query":     req.query,
            "age_group": req.age_group,
            "history":   req.history,
            "metadata":  req.metadata,
        },
    )

    result = await agent.process_task(message)

    return YouthSessionResponse(
        session_id=result.get("session", {}).get("session_id", message.message_id),
        agent_id=result.get("agent_id", req.agent_id),
        display_name=result.get("display_name", ""),
        age_group=result.get("age_group", req.age_group),
        safety_level=result.get("session", {}).get("safety_level", "green"),
        response=result.get("response", ""),
        status=result.get("status", "ok"),
    )


@youth_router.get("/safety/dashboard", tags=["youth"])
async def parent_safety_dashboard(request: Request) -> dict[str, Any]:
    """
    Dashboard Trendów dla rodziców (§9.3).
    Zwraca anomalie – BEZ treści rozmów.
    """
    coordinator = getattr(request.app.state, "safety_coordinator", None)
    if coordinator is None:
        return {"total_alerts": 0, "critical_alerts": 0, "recent_alerts": []}
    return coordinator.get_parent_dashboard()


# ===========================================================================
# Router: Exotic / Niche Agents (Kompendium Anomalii Agentowych)
# ===========================================================================

class ExoticSessionRequest(BaseModel):
    """Żądanie sesji z egzotycznym agentem."""
    agent_id: str = Field(..., description="ID agenta egzotycznego")
    task: str = Field(..., min_length=1, max_length=2000,
                      description="Zapytanie / zadanie dla agenta")


class ExoticSessionResponse(BaseModel):
    """Odpowiedź agenta egzotycznego."""
    session_id:   str
    agent_id:     str
    display_name: str
    category:     str
    safety:       str
    response:     str
    status:       str = "ok"


exotic_router = APIRouter(prefix="/exotic", tags=["exotic"])


@exotic_router.get("/agents", tags=["exotic"])
async def list_exotic_agents(request: Request) -> list[dict[str, Any]]:
    """
    Zwraca listę wszystkich agentów egzotycznych (§1–§7 Kompendium).
    """
    exotic_agents = getattr(request.app.state, "exotic_agents", {})
    return [a.get_info() for a in exotic_agents.values()]


@exotic_router.post("/session", response_model=ExoticSessionResponse)
async def exotic_session(
    req: ExoticSessionRequest, request: Request
) -> ExoticSessionResponse:
    """
    Uruchamia sesję z wybranym agentem egzotycznym.

    Agenty z safety=sandboxed (ChaosGPT, Tay, Alice&Bob) działają wyłącznie
    w trybie analitycznym – nie generują szkodliwych treści.
    """
    exotic_agents = getattr(request.app.state, "exotic_agents", {})
    agent = exotic_agents.get(req.agent_id)
    if agent is None:
        available = list(exotic_agents.keys())
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Agent egzotyczny '{req.agent_id}' nie istnieje.",
                "available": available,
            },
        )

    message = AgentMessage(
        type=MessageType.TASK_REQUEST,
        sender_id="api",
        receiver_id=req.agent_id,
        payload={"task": req.task},
    )

    result = await agent.process_task(message)

    return ExoticSessionResponse(
        session_id=result.get("session", {}).get("session_id", message.message_id),
        agent_id=result.get("agent_id", req.agent_id),
        display_name=result.get("display_name", ""),
        category=result.get("category", ""),
        safety=result.get("safety", "safe"),
        response=result.get("response", ""),
        status=result.get("status", "ok"),
    )


# ===========================================================================
# Router: Agent Registry (6666 unikalnych agentów)
# ===========================================================================

class RegistrySessionRequest(BaseModel):
    """Żądanie sesji z agentem z rejestru 6666."""
    agent_id: str = Field(..., description="ID agenta z rejestru (np. 'agent_0001')")
    task: str = Field(..., min_length=1, max_length=2000,
                      description="Zapytanie / zadanie dla agenta")


class RegistrySessionResponse(BaseModel):
    """Odpowiedź agenta z rejestru."""
    agent_id:       str
    display_name:   str
    category:       str
    safety:         str
    domain:         str
    role:           str
    specialization: str
    response:       str
    status:         str = "ok"


registry_router = APIRouter(prefix="/registry", tags=["registry"])


@registry_router.get("/agents", tags=["registry"])
async def list_registry_agents(
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Zwraca stronicowaną listę agentów z rejestru 6666.

    Parametry:
        offset: pozycja startowa (domyślnie 0)
        limit:  liczba wyników (domyślnie 100, maks. 500)
    """
    from src.agents.agent_registry import get_default_registry
    registry = get_default_registry()
    limit = min(limit, 500)
    entries = registry.page(offset=offset, limit=limit)
    return {
        "total":   registry.count(),
        "offset":  offset,
        "limit":   limit,
        "agents":  [e.to_dict() for e in entries],
    }


@registry_router.get("/agents/search", tags=["registry"])
async def search_registry_agents(
    q: str,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Wyszukuje agentów po frazie (display_name, domain, role, specialization).
    """
    from src.agents.agent_registry import get_default_registry
    registry = get_default_registry()
    limit = min(limit, 500)
    entries = registry.search(q, limit=limit)
    return {
        "query":   q,
        "count":   len(entries),
        "agents":  [e.to_dict() for e in entries],
    }


@registry_router.get("/agents/{agent_id}", tags=["registry"])
async def get_registry_agent(agent_id: str) -> dict[str, Any]:
    """
    Zwraca szczegóły agenta po jego ID.
    """
    from src.agents.agent_registry import get_default_registry
    registry = get_default_registry()
    entry = registry.get(agent_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' nie istnieje w rejestrze.",
        )
    return entry.to_dict()


@registry_router.post("/session", response_model=RegistrySessionResponse)
async def registry_session(
    req: RegistrySessionRequest, request: Request
) -> RegistrySessionResponse:
    """
    Uruchamia sesję z wybranym agentem z rejestru 6666.
    """
    from src.agents.agent_registry import get_default_registry, DynamicRegistryAgent
    registry = get_default_registry()
    entry = registry.get(req.agent_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{req.agent_id}' nie istnieje w rejestrze.",
        )

    broker = getattr(request.app.state, "broker", None)
    if broker is None:
        raise HTTPException(status_code=503, detail="Broker niedostępny.")

    agent = DynamicRegistryAgent(entry=entry, broker=broker)
    message = AgentMessage(
        type=MessageType.TASK_REQUEST,
        sender_id="api",
        receiver_id=req.agent_id,
        payload={"task": req.task},
    )
    result = await agent.process_task(message)

    return RegistrySessionResponse(
        agent_id      = result.get("agent_id", req.agent_id),
        display_name  = result.get("display_name", ""),
        category      = result.get("category", ""),
        safety        = result.get("safety", "safe"),
        domain        = result.get("domain", ""),
        role          = result.get("role", ""),
        specialization= result.get("specialization", ""),
        response      = result.get("response", ""),
    )


# ===========================================================================
# Helper: ładowanie danych historycznych agentów
# ===========================================================================

def _load_historical_agents() -> list[dict]:
    """Ładuje dane z data/historical_agents.json."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent.parent / "data" / "historical_agents.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ===========================================================================
# Router: Historical AI Catalog
# ===========================================================================

historical_router = APIRouter(prefix="/historical", tags=["historical"])


@historical_router.get("/agents", tags=["historical"])
async def list_historical_agents(
    type_filter: str = "",
    org_filter:  str = "",
    open_source: bool | None = None,
    offset: int = 0,
    limit:  int = 50,
) -> dict[str, Any]:
    """
    Zwraca katalog historycznych modeli i agentów AI (151+ wpisów).

    Parametry filtrowania:
        type_filter  : LLM, Vision, Audio, Video, Agent, Chatbot, …
        org_filter   : OpenAI, Google, Meta AI, …
        open_source  : true / false
    """
    agents = _load_historical_agents()
    if type_filter:
        agents = [a for a in agents if type_filter.lower() in a.get("type", "").lower()]
    if org_filter:
        agents = [a for a in agents if org_filter.lower() in a.get("org", "").lower()]
    if open_source is not None:
        agents = [a for a in agents if a.get("open_source") == open_source]
    total = len(agents)
    limit = min(limit, 500)
    return {
        "total":   total,
        "offset":  offset,
        "limit":   limit,
        "agents":  agents[offset: offset + limit],
    }


@historical_router.get("/agents/{agent_id}", tags=["historical"])
async def get_historical_agent(agent_id: str) -> dict[str, Any]:
    """Zwraca szczegóły historycznego agenta po jego ID."""
    agents = _load_historical_agents()
    for a in agents:
        if a.get("id") == agent_id:
            return a
    raise HTTPException(status_code=404, detail=f"Historyczny agent '{agent_id}' nieznany.")


@historical_router.get("/stats", tags=["historical"])
async def historical_stats() -> dict[str, Any]:
    """Statystyki katalogu historycznych agentów."""
    agents = _load_historical_agents()
    types: dict[str, int] = {}
    orgs:  dict[str, int] = {}
    for a in agents:
        t = a.get("type", "Unknown")
        o = a.get("org", "Unknown")
        types[t] = types.get(t, 0) + 1
        orgs[o]  = orgs.get(o, 0) + 1
    open_count = sum(1 for a in agents if a.get("open_source"))
    return {
        "total":        len(agents),
        "open_source":  open_count,
        "closed_source":len(agents) - open_count,
        "by_type":      dict(sorted(types.items(), key=lambda x: -x[1])),
        "by_org":       dict(sorted(orgs.items(),  key=lambda x: -x[1])[:20]),
    }


# ===========================================================================
# Router: Agent Builder (Pro Code / No Code / Hybrid)
# ===========================================================================

class BuildNoCodeRequest(BaseModel):
    display_name:         str = Field(..., min_length=2, max_length=100)
    domain:               str
    role:                 str
    specialization:       str
    category:             str = "specialist"
    safety:               str = "safe"
    extra_instructions:   str = ""


class BuildProCodeRequest(BaseModel):
    display_name:   str = Field(..., min_length=2)
    domain:         str
    role:           str
    specialization: str
    mission:        str
    system_prompt:  str = Field(..., min_length=10)
    category:       str = "specialist"
    safety:         str = "safe"
    custom_code:    str = ""
    tools:          list[str] = []
    metadata:       dict[str, Any] = {}


class BuildHybridRequest(BaseModel):
    display_name:          str = Field(..., min_length=2)
    domain:                str
    role:                  str
    specialization:        str
    category:              str = "specialist"
    safety:                str = "safe"
    system_prompt_override: str = ""
    custom_code:           str = ""
    tools:                 list[str] = []
    metadata:              dict[str, Any] = {}


class CustomAgentResponse(BaseModel):
    agent_id:       str
    display_name:   str
    domain:         str
    role:           str
    specialization: str
    mission:        str
    category:       str
    safety:         str
    builder_mode:   str
    created_at:     str


builder_router = APIRouter(prefix="/builder", tags=["builder"])


@builder_router.get("/options", tags=["builder"])
async def get_builder_options() -> dict[str, Any]:
    """Zwraca dostępne opcje formularza No-Code."""
    from src.agents.agent_builder import NoCodeBuilder
    return NoCodeBuilder.get_form_options()


@builder_router.post("/no-code", response_model=CustomAgentResponse)
async def build_no_code(req: BuildNoCodeRequest, request: Request) -> CustomAgentResponse:
    """Tworzy agenta za pomocą formularza No-Code."""
    from src.agents.agent_builder import NoCodeBuilder, CustomAgentStore
    user = _get_current_user(request)
    try:
        builder = NoCodeBuilder()
        spec    = builder.build(
            display_name       = req.display_name,
            domain             = req.domain,
            role               = req.role,
            specialization     = req.specialization,
            category           = req.category,
            safety             = req.safety,
            extra_instructions = req.extra_instructions,
            created_by         = user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    CustomAgentStore().add(spec)
    return _spec_to_response(spec)


@builder_router.post("/pro-code", response_model=CustomAgentResponse)
async def build_pro_code(req: BuildProCodeRequest, request: Request) -> CustomAgentResponse:
    """Tworzy agenta z pełnej specyfikacji JSON (Pro Code)."""
    from src.agents.agent_builder import ProCodeBuilder, CustomAgentStore
    user = _get_current_user(request)
    try:
        builder = ProCodeBuilder()
        spec    = builder.build(
            payload    = req.model_dump(),
            created_by = user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    CustomAgentStore().add(spec)
    return _spec_to_response(spec)


@builder_router.post("/hybrid", response_model=CustomAgentResponse)
async def build_hybrid(req: BuildHybridRequest, request: Request) -> CustomAgentResponse:
    """Tworzy agenta hybrydowego (formularz + opcjonalne nadpisania)."""
    from src.agents.agent_builder import HybridBuilder, CustomAgentStore
    user = _get_current_user(request)
    try:
        builder = HybridBuilder()
        spec    = builder.build(
            display_name          = req.display_name,
            domain                = req.domain,
            role                  = req.role,
            specialization        = req.specialization,
            category              = req.category,
            safety                = req.safety,
            system_prompt_override= req.system_prompt_override,
            custom_code           = req.custom_code,
            tools                 = req.tools or None,
            metadata              = req.metadata or None,
            created_by            = user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    CustomAgentStore().add(spec)
    return _spec_to_response(spec)


@builder_router.get("/agents", tags=["builder"])
async def list_custom_agents(offset: int = 0, limit: int = 50) -> dict[str, Any]:
    """Zwraca listę agentów zbudowanych przez użytkownika."""
    from src.agents.agent_builder import CustomAgentStore
    store = CustomAgentStore()
    limit = min(limit, 200)
    return {
        "total":  store.count(),
        "offset": offset,
        "limit":  limit,
        "agents": [a.to_dict() for a in store.page(offset, limit)],
    }


@builder_router.get("/agents/{agent_id}", tags=["builder"])
async def get_custom_agent(agent_id: str) -> dict[str, Any]:
    """Zwraca szczegóły custom agenta."""
    from src.agents.agent_builder import CustomAgentStore
    spec = CustomAgentStore().get(agent_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Custom agent '{agent_id}' nieznany.")
    return spec.to_dict()


@builder_router.delete("/agents/{agent_id}", tags=["builder"])
async def delete_custom_agent(agent_id: str) -> dict[str, str]:
    """Usuwa custom agenta."""
    from src.agents.agent_builder import CustomAgentStore
    if not CustomAgentStore().delete(agent_id):
        raise HTTPException(status_code=404, detail=f"Custom agent '{agent_id}' nieznany.")
    return {"status": "deleted", "agent_id": agent_id}


def _spec_to_response(spec: Any) -> "CustomAgentResponse":
    return CustomAgentResponse(
        agent_id      = spec.agent_id,
        display_name  = spec.display_name,
        domain        = spec.domain,
        role          = spec.role,
        specialization= spec.specialization,
        mission       = spec.mission,
        category      = spec.category,
        safety        = spec.safety,
        builder_mode  = spec.builder_mode,
        created_at    = spec.created_at,
    )


def _get_current_user(request: Request) -> str:
    """Pobiera email użytkownika z JWT Bearer token (opcjonalne)."""
    try:
        from src.api.auth import get_google_auth_service
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token   = auth_header[7:]
            service = get_google_auth_service()
            payload = service.verify_session_jwt(token)
            return payload.get("email", "anonymous")
    except (ValueError, KeyError):
        pass
    return "anonymous"


# ===========================================================================
# Router: Google OAuth2 Authentication
# ===========================================================================

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.get("/google", tags=["auth"])
async def google_login() -> dict[str, str]:
    """
    Zwraca URL do logowania przez Google.

    Jeśli GOOGLE_CLIENT_ID nie jest skonfigurowany, zwraca URL demo.
    """
    from src.api.auth import get_google_auth_service
    service = get_google_auth_service()
    if not service.is_configured:
        return {
            "status": "demo",
            "message": "GOOGLE_CLIENT_ID nie ustawiony – użyj /auth/google/demo",
            "demo_url": "/api/v1/auth/google/demo",
        }
    import secrets
    state = secrets.token_urlsafe(16)
    url   = service.get_authorization_url(state=state)
    return {"status": "ok", "auth_url": url}


@auth_router.get("/google/callback", tags=["auth"])
async def google_callback(code: str, state: str = "") -> dict[str, str]:
    """
    Obsługuje callback OAuth2 od Google.
    Wymienia authorization_code na JWT sesji.
    """
    from src.api.auth import get_google_auth_service
    service = get_google_auth_service()
    if not service.is_configured:
        raise HTTPException(status_code=503, detail="Google OAuth nie skonfigurowany.")
    try:
        token_data = await service.exchange_code(code)
        user_info  = await service.get_user_info(token_data["access_token"])
        jwt_token  = service.create_session_jwt(user_info)
        return {
            "status":       "ok",
            "access_token": jwt_token,
            "token_type":   "Bearer",
            "email":        user_info.get("email", ""),
            "name":         user_info.get("name", ""),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OAuth błąd: {exc}") from exc


@auth_router.get("/google/demo", tags=["auth"])
async def google_demo_token(email: str = "demo@czlowiek-roku.local") -> dict[str, str]:
    """
    Generuje token demo (bez prawdziwego logowania Google).
    Używany w środowiskach deweloperskich bez GOOGLE_CLIENT_ID.
    """
    from src.api.auth import get_google_auth_service
    service   = get_google_auth_service()
    jwt_token = service.get_demo_token(email=email)
    return {
        "status":       "demo",
        "access_token": jwt_token,
        "token_type":   "Bearer",
        "email":        email,
        "note":         "Token demonstracyjny – nie używaj w produkcji.",
    }


@auth_router.get("/me", tags=["auth"])
async def get_current_user(request: Request) -> dict[str, Any]:
    """
    Zwraca profil zalogowanego użytkownika z JWT Bearer token.
    """
    from src.api.auth import get_google_auth_service
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Brak tokenu Bearer.")
    token = auth_header[7:]
    try:
        service = get_google_auth_service()
        payload = service.verify_session_jwt(token)
        return {
            "sub":     payload.get("sub", ""),
            "email":   payload.get("email", ""),
            "name":    payload.get("name", ""),
            "picture": payload.get("picture", ""),
        }
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@auth_router.post("/logout", tags=["auth"])
async def logout() -> dict[str, str]:
    """Informuje o wylogowaniu (klient usuwa token lokalnie)."""
    return {
        "status": "logged_out",
        "message": "Usuń token JWT po stronie klienta.",
    }


# ===========================================================================
# Router: MCP (Model Context Protocol) Server
# ===========================================================================

mcp_router = APIRouter(prefix="/mcp", tags=["mcp"])


@mcp_router.post("/rpc", tags=["mcp"])
async def mcp_rpc(body: dict[str, Any]) -> dict[str, Any]:
    """
    Główny endpoint JSON-RPC 2.0 dla serwera MCP.

    Obsługuje metody:
      initialize, tools/list, tools/call,
      resources/list, resources/read,
      prompts/list, prompts/get, ping
    """
    from src.mcp.server import get_mcp_server
    server = get_mcp_server()
    return await server.handle_request(body)


@mcp_router.get("/info", tags=["mcp"])
async def mcp_info() -> dict[str, Any]:
    """Zwraca informacje o serwerze MCP."""
    from src.mcp.server import get_mcp_server
    server = get_mcp_server()
    return {
        "name":    server.name,
        "version": server.version,
        "protocol": "2024-11-05",
        "transport": "HTTP JSON-RPC 2.0",
        "endpoint": "/api/v1/mcp/rpc",
    }


@mcp_router.get("/tools", tags=["mcp"])
async def mcp_list_tools() -> dict[str, Any]:
    """Zwraca listę dostępnych narzędzi MCP."""
    from src.mcp.server import get_mcp_server
    server = get_mcp_server()
    result = await server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    return result.get("result", {})


@mcp_router.get("/resources", tags=["mcp"])
async def mcp_list_resources() -> dict[str, Any]:
    """Zwraca listę zasobów MCP."""
    from src.mcp.server import get_mcp_server
    server = get_mcp_server()
    result = await server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}})
    return result.get("result", {})
