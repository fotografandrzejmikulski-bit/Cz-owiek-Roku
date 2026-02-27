"""
FastAPI backend – REST + WebSocket API dla klientów cross-platform.

Architektura:
  - /api/v1/tasks  : REST endpoint do zlecania zadań orkiestratorowi
  - /ws            : WebSocket kanał do odbierania wyników w czasie rzeczywistym
  - /api/v1/agents : status agentów

Komunikacja asynchroniczna zapewnia, że UI klienta nie jest blokowane.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.agents import (
    AnalyticsAgent,
    ContentAgent,
    DeepResearchOrchestrator,
    NarrativeAgent,
    OrchestratorAgent,
    create_all_edu_agents,
    create_all_specialist_agents,
)
from src.api.routers import (
    agents_router,
    chat_router,
    edu_router,
    pcg_router,
    research_router,
    specialist_router,
    tasks_router,
)
from src.communication.broker import MessageBroker
from src.models.message import AgentMessage, MessageType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Globalny broker i orkiestrator (singleton w procesie)
# ---------------------------------------------------------------------------
broker = MessageBroker()
orchestrator = OrchestratorAgent(broker=broker)
_agent_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Uruchom / zatrzymaj agentów razem z aplikacją."""
    # Wyczyść stare zadania przed ponownym uruchomieniem (np. w testach)
    _agent_tasks.clear()

    content_agent = ContentAgent(broker=broker)
    narrative_agent = NarrativeAgent(broker=broker)
    analytics_agent = AnalyticsAgent(broker=broker)
    deep_research_agent = DeepResearchOrchestrator(broker=broker)

    # Educational agents (AAK – Cyfrowa Agora Wiedzy) – 17 single-instance + 6 Polyglot
    edu_agents_list = create_all_edu_agents(broker=broker)
    edu_agents_dict = {a.agent_id: a for a in edu_agents_list}

    # Specialist agents – 6 domain experts
    specialist_agents_list = create_all_specialist_agents(broker=broker)
    specialist_agents_dict = {a.agent_id: a for a in specialist_agents_list}

    for agent in (content_agent, narrative_agent, analytics_agent):
        orchestrator.register_agent(agent.agent_id, agent.get_capabilities())
    # Register DeepResearchOrchestrator directly (not through main orchestrator pipeline)
    orchestrator.register_agent(
        deep_research_agent.agent_id, deep_research_agent.get_capabilities()
    )

    agents_to_start = [
        orchestrator, content_agent, narrative_agent,
        analytics_agent, deep_research_agent,
        *edu_agents_list,
        *specialist_agents_list,
    ]
    for agent in agents_to_start:
        task = asyncio.create_task(agent.start())
        _agent_tasks.append(task)

    # Przekaż zależności do routerów przez state aplikacji
    app.state.broker = broker
    app.state.orchestrator = orchestrator
    app.state.edu_agents = edu_agents_dict
    app.state.specialist_agents = specialist_agents_dict

    logger.info(
        "System MAS uruchomiony z %d agentami (%d edu, %d specialist).",
        len(agents_to_start),
        len(edu_agents_list),
        len(specialist_agents_list),
    )
    yield

    for task in _agent_tasks:
        task.cancel()
    await asyncio.gather(*_agent_tasks, return_exceptions=True)
    logger.info("System MAS zatrzymany.")


# ---------------------------------------------------------------------------
# Aplikacja FastAPI
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Człowiek Roku – MAS Backend",
    version="1.0.0",
    description=(
        "Backend systemu wieloagentowego (MAS) dla gry AAA 'Człowiek Roku'. "
        "Udostępnia REST API i WebSocket dla klientów Android/Windows."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")
app.include_router(edu_router, prefix="/api/v1")
app.include_router(specialist_router, prefix="/api/v1")
app.include_router(pcg_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# WebSocket – push wiadomości do klientów w czasie rzeczywistym
# ---------------------------------------------------------------------------
class ConnectionManager:
    """Zarządza aktywnymi połączeniami WebSocket (Observer)."""

    def __init__(self) -> None:
        self._active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active.append(websocket)
        logger.info("Nowy klient WebSocket połączony. Aktywne: %d", len(self._active))

    def disconnect(self, websocket: WebSocket) -> None:
        self._active.remove(websocket)

    async def broadcast(self, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._active.remove(ws)


ws_manager = ConnectionManager()


async def _forward_to_ws(message: AgentMessage) -> None:
    """Callback brokera – przekaż wiadomość broadcast do wszystkich WS."""
    await ws_manager.broadcast(message.to_dict())


# Zarejestruj forward zaraz po starcie modułu (broker już istnieje)
broker.subscribe_broadcast(_forward_to_ws)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    Kanał WebSocket dla klientów Android/Windows.
    Klient odbiera wyniki zadań bez pollingu.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Oczekuj na wiadomości od klienta (np. zlecenia zadań przez WS)
            data = await websocket.receive_json()
            message = AgentMessage(
                type=MessageType.TASK_REQUEST,
                sender_id=data.get("client_id", "ws_client"),
                receiver_id="orchestrator",
                payload=data.get("payload", {}),
            )
            await broker.publish(message)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("Klient WebSocket rozłączony.")
