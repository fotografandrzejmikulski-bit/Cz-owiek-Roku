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
