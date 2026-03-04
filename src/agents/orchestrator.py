"""
Agent Orkiestrator – centralny koordynator roju agentów.
Implementuje wzorzec Mediator na poziomie zadań:
  - przyjmuje żądania od klientów (API/WebSocket)
  - rozkłada złożone zadania na podzadania
  - deleguje je do wyspecjalizowanych agentów
  - agreguje wyniki i odsyła do klienta
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

from src.agents.base_agent import BaseAgent
from src.models.message import AgentMessage, AgentStatus, MessageType

if TYPE_CHECKING:
    from src.communication.broker import MessageBroker

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """
    Orkiestrator zarządza flotą wyspecjalizowanych agentów.

    Odpowiedzialności:
    1. Rejestracja i monitorowanie agentów podrzędnych.
    2. Planowanie sekwencji zadań (pipeline).
    3. Agregacja wyników cząstkowych.
    4. Obsługa awarii agentów (circuit-breaker).
    """

    def __init__(self, broker: "MessageBroker") -> None:
        super().__init__(agent_id="orchestrator", role="orchestrator", broker=broker)
        # agent_id -> metadane (możliwości, ostatni heartbeat, status)
        self._registry: dict[str, dict[str, Any]] = {}
        # correlation_id -> future (czekamy na wynik)
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Rejestracja agentów
    # ------------------------------------------------------------------
    def register_agent(
        self, agent_id: str, capabilities: list[str]
    ) -> None:
        """Zarejestruj agenta podrzędnego z jego możliwościami."""
        self._registry[agent_id] = {
            "capabilities": capabilities,
            "status": AgentStatus.IDLE,
            "last_seen": None,
        }
        logger.info(
            "[Orchestrator] Zarejestrowano agenta '%s' z możliwościami: %s",
            agent_id, capabilities,
        )

    # ------------------------------------------------------------------
    # Implementacja process_task (Strategy)
    # ------------------------------------------------------------------
    async def process_task(self, message: AgentMessage) -> dict[str, Any]:
        """
        Orkiestrator rozkłada zadanie na podzadania i deleguje je.
        Zwraca zagregowany wynik.
        """
        task_type = message.payload.get("task_type", "unknown")
        logger.info(
            "[Orchestrator] Obsługuję zadanie '%s' od '%s'.",
            task_type, message.sender_id,
        )

        pipeline = self._build_pipeline(task_type, message.payload)
        results: list[dict[str, Any]] = []

        for step in pipeline:
            agent_id = self._select_agent(step["capability"])
            if agent_id is None:
                logger.warning(
                    "[Orchestrator] Brak agenta dla możliwości '%s'.",
                    step["capability"],
                )
                continue
            result = await self._delegate(
                agent_id=agent_id,
                task_payload={**step["payload"], "context": results},
            )
            results.append(result)

        return {"pipeline_results": results, "task_type": task_type}

    # ------------------------------------------------------------------
    # Obsługa heartbeatów i aktualizacji statusów
    # ------------------------------------------------------------------
    async def _handle_message(self, message: AgentMessage) -> None:
        if message.type == MessageType.AGENT_STATUS:
            agent_id = message.sender_id
            if agent_id in self._registry:
                self._registry[agent_id]["status"] = message.payload.get(
                    "status", AgentStatus.IDLE
                )
            return

        if message.type == MessageType.TASK_RESULT:
            correlation_id = message.correlation_id
            if correlation_id and correlation_id in self._pending:
                future = self._pending.pop(correlation_id)
                if not future.done():
                    future.set_result(message.payload)
            return

        await super()._handle_message(message)

    # ------------------------------------------------------------------
    # Prywatne metody pomocnicze
    # ------------------------------------------------------------------
    def _build_pipeline(
        self, task_type: str, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Proste mapowanie typów zadań na kroki pipeline'u.
        W produkcji: silnik reguł lub LLM-based planner.
        """
        pipelines: dict[str, list[dict[str, Any]]] = {
            "generate_content": [
                {
                    "capability": "narrative",
                    "payload": {"action": "generate_story", "params": payload},
                },
                {
                    "capability": "content",
                    "payload": {"action": "enrich_content", "params": payload},
                },
            ],
            "analytics": [
                {
                    "capability": "analytics",
                    "payload": {"action": "analyze", "params": payload},
                },
            ],
            "deep_research": [
                {
                    "capability": "deep_research",
                    "payload": {**payload},
                },
            ],
        }
        return pipelines.get(task_type, [])

    def _select_agent(self, capability: str) -> str | None:
        """Wybierz agenta z daną możliwością (round-robin dla uproszenia)."""
        for agent_id, meta in self._registry.items():
            if (
                capability in meta.get("capabilities", [])
                and meta.get("status") != AgentStatus.OFFLINE
            ):
                return agent_id
        return None

    async def _delegate(
        self, agent_id: str, task_payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Wyślij podzadanie do agenta i poczekaj na wynik (async)."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()

        request = AgentMessage(
            type=MessageType.TASK_REQUEST,
            sender_id=self._agent_id,
            receiver_id=agent_id,
            payload=task_payload,
        )
        self._pending[request.message_id] = future

        await self._broker.publish(request)

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._pending.pop(request.message_id, None)
            logger.error(
                "[Orchestrator] Timeout czekania na agenta '%s'.", agent_id
            )
            return {"error": "timeout", "agent_id": agent_id}

    def get_capabilities(self) -> list[str]:
        return ["orchestration", "planning", "delegation"]
