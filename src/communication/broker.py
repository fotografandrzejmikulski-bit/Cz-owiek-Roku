"""
Broker wiadomości – abstrakcja nad systemem kolejkowania.
Implementuje wzorzec Mediator: agenci nie znają się nawzajem,
komunikują się wyłącznie przez brokera.

Obsługuje:
  - tryb in-process (asyncio.Queue) – dla środowisk deweloperskich
  - tryb zewnętrzny (RabbitMQ/Kafka) – dla produkcji (rozszerzalny)
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Awaitable

from src.models.message import AgentMessage, MessageType

logger = logging.getLogger(__name__)

MessageHandler = Callable[[AgentMessage], Awaitable[None]]


class MessageBroker:
    """
    Lokalny broker wiadomości oparty na asyncio.

    Wzorzec Mediator – centralne miejsce routingu komunikatów
    między agentami bez bezpośrednich zależności między nimi.
    """

    def __init__(self) -> None:
        # agent_id -> lista callbacków (subskrybentów)
        self._subscribers: dict[str, list[MessageHandler]] = defaultdict(list)
        # Dedykowana kolejka dla wiadomości broadcast
        self._broadcast_handlers: list[MessageHandler] = []

    async def subscribe(self, agent_id: str, handler: MessageHandler) -> None:
        """Zarejestruj agenta jako odbiorcę wiadomości."""
        self._subscribers[agent_id].append(handler)
        logger.debug("Zasubskrybowano agenta '%s'.", agent_id)

    async def unsubscribe(self, agent_id: str) -> None:
        """Wyrejestruj agenta z brokera."""
        self._subscribers.pop(agent_id, None)
        logger.debug("Wyrejestrowano agenta '%s'.", agent_id)

    def subscribe_broadcast(self, handler: MessageHandler) -> None:
        """Subskrybuj wiadomości broadcast (np. do WebSocket klientów)."""
        self._broadcast_handlers.append(handler)

    async def publish(self, message: AgentMessage) -> None:
        """
        Opublikuj wiadomość. Routing:
        - BROADCAST -> wszystkie zarejestrowane handlery broadcast
        - pozostałe -> docelowy agent (receiver_id) lub broadcast jeśli None
        """
        if message.type == MessageType.BROADCAST or message.receiver_id is None:
            await self._deliver_broadcast(message)
        else:
            await self._deliver_direct(message)

    async def _deliver_direct(self, message: AgentMessage) -> None:
        """Dostarcz wiadomość bezpośrednio do odbiorcy."""
        handlers = self._subscribers.get(message.receiver_id or "", [])
        if not handlers:
            logger.warning(
                "Brak subskrybentów dla agenta '%s'. Wiadomość odrzucona.",
                message.receiver_id,
            )
            return
        await asyncio.gather(*[h(message) for h in handlers])

    async def _deliver_broadcast(self, message: AgentMessage) -> None:
        """Dostarcz wiadomość do wszystkich subskrybentów broadcast."""
        all_handlers = [
            h for handlers in self._subscribers.values() for h in handlers
        ] + self._broadcast_handlers
        if all_handlers:
            await asyncio.gather(*[h(message) for h in all_handlers])
