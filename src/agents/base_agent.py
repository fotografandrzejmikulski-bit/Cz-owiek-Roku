"""
Abstrakcyjna klasa bazowa dla wszystkich agentów w systemie MAS.
Implementuje wzorzec Strategy (każdy agent definiuje własną logikę),
Observer (subskrypcja wiadomości) oraz zasady SOLID.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.models.message import AgentMessage, AgentStatus, MessageType

if TYPE_CHECKING:
    from src.communication.broker import MessageBroker

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Bazowy agent systemu wieloagentowego (MAS).

    Każdy agent:
    - ma unikalny identyfikator i rolę
    - subskrybuje wiadomości przez brokera (Observer)
    - przetwarza zadania asynchronicznie, nie blokując UI
    - raportuje swój status
    """

    def __init__(self, agent_id: str, role: str, broker: "MessageBroker") -> None:
        self._agent_id = agent_id
        self._role = role
        self._broker = broker
        self._status = AgentStatus.IDLE
        self._started_at: datetime | None = None
        self._task_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()

    # ------------------------------------------------------------------
    # Properties (read-only eksport stanu)
    # ------------------------------------------------------------------
    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def role(self) -> str:
        return self._role

    @property
    def status(self) -> AgentStatus:
        return self._status

    # ------------------------------------------------------------------
    # Cykl życia agenta
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Uruchom agenta – zarejestruj się w brokerze i wejdź w pętlę."""
        self._status = AgentStatus.IDLE
        self._started_at = datetime.now(timezone.utc)
        await self._broker.subscribe(self._agent_id, self._enqueue)
        logger.info("[%s] Agent '%s' uruchomiony.", self._role, self._agent_id)
        await self._run_loop()

    async def stop(self) -> None:
        """Zatrzymaj agenta."""
        self._status = AgentStatus.OFFLINE
        await self._broker.unsubscribe(self._agent_id)
        logger.info("[%s] Agent '%s' zatrzymany.", self._role, self._agent_id)

    # ------------------------------------------------------------------
    # Obsługa wiadomości
    # ------------------------------------------------------------------
    async def _enqueue(self, message: AgentMessage) -> None:
        """Callback brokera – wiadomość trafia do kolejki (nie blokuje)."""
        await self._task_queue.put(message)

    async def _run_loop(self) -> None:
        """Główna pętla przetwarzania – asynchroniczna, nie blokuje UI."""
        while self._status != AgentStatus.OFFLINE:
            try:
                message = await asyncio.wait_for(
                    self._task_queue.get(), timeout=1.0
                )
                await self._handle_message(message)
            except asyncio.TimeoutError:
                await self._heartbeat()
            except Exception as exc:
                logger.exception(
                    "[%s] Błąd w pętli agenta '%s': %s",
                    self._role, self._agent_id, exc,
                )
                self._status = AgentStatus.ERROR

    async def _handle_message(self, message: AgentMessage) -> None:
        """Routing wiadomości przychodzących do odpowiednich handlerów."""
        if message.type == MessageType.TASK_REQUEST:
            self._status = AgentStatus.RUNNING
            try:
                result = await self.process_task(message)
                await self._publish_result(result, message)
            finally:
                self._status = AgentStatus.IDLE
        elif message.type == MessageType.HEARTBEAT:
            await self._heartbeat()

    async def _publish_result(
        self, result: dict[str, Any], original: AgentMessage
    ) -> None:
        """Opublikuj wynik zadania z powrotem przez brokera."""
        response = AgentMessage(
            type=MessageType.TASK_RESULT,
            sender_id=self._agent_id,
            receiver_id=original.sender_id,
            correlation_id=original.message_id,
            payload=result,
        )
        await self._broker.publish(response)

    async def _heartbeat(self) -> None:
        """Wyślij sygnał życia do orkiestratora."""
        hb = AgentMessage(
            type=MessageType.AGENT_STATUS,
            sender_id=self._agent_id,
            receiver_id="orchestrator",
            payload={"status": self._status.value, "role": self._role},
        )
        await self._broker.publish(hb)

    # ------------------------------------------------------------------
    # Interfejs do implementacji przez klasy pochodne (Strategy)
    # ------------------------------------------------------------------
    @abstractmethod
    async def process_task(self, message: AgentMessage) -> dict[str, Any]:
        """
        Główna logika agenta. Musi być zaimplementowana przez podklasę.

        Args:
            message: Wiadomość z zadaniem do wykonania.

        Returns:
            Słownik z wynikami zadania.
        """

    def get_capabilities(self) -> list[str]:
        """Zwróć listę możliwości agenta (używane przez orkiestratora)."""
        return []
