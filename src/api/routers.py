"""
Routery FastAPI dla zasobów REST API.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
