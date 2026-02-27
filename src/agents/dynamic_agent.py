"""
Agent Dynamiczny – tworzony w czasie wykonania przez Builders Agentów.

Pozwala rejestrować nowych agentów bez modyfikacji kodu, wyłącznie przez
wywołanie REST API (POST /api/v1/agents/).  Każdy DynamicAgent:
  - ma własną tożsamość (agent_id, role, capabilities)
  - opcjonalnie korzysta z LLM do przetwarzania dowolnych zadań
  - natychmiast rejestruje się w brokerze i orkiestratorze

Wzorzec: Prototype / Factory – jeden szablon, wiele instancji.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from src.agents.base_agent import BaseAgent
from src.communication.llm_client import BaseLlmClient, create_llm_client
from src.models.message import AgentMessage

if TYPE_CHECKING:
    from src.communication.broker import MessageBroker

logger = logging.getLogger(__name__)


class DynamicAgent(BaseAgent):
    """
    Uniwersalny agent konfigurowany w czasie wykonania.

    Parametry:
        agent_id:    Unikalny identyfikator (np. „quest_agent_1")
        role:        Rola / krótka nazwa (np. „quest_designer")
        capabilities: Lista możliwości (używane przez orkiestratora do routingu)
        description: Opis działania agenta (używany jako system-prompt w LLM)
        broker:      Broker wiadomości
        llm_client:  Opcjonalny klient LLM; domyślnie tworzony z ustawień
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        capabilities: list[str],
        description: str,
        broker: "MessageBroker",
        llm_client: BaseLlmClient | None = None,
    ) -> None:
        super().__init__(agent_id=agent_id, role=role, broker=broker)
        self._capabilities = capabilities
        self._description = description
        self._llm = llm_client or create_llm_client()

    # ------------------------------------------------------------------
    # Strategy: obsługa zadania przez LLM z opisem agenta jako kontekstem
    # ------------------------------------------------------------------

    async def process_task(self, message: AgentMessage) -> dict[str, Any]:
        """Przetwarza dowolne zadanie używając LLM z kontekstem roli."""
        action = message.payload.get("action", "")
        chat_text = message.payload.get("chat_text", "")
        params = message.payload.get("params", {})

        logger.info(
            "[DynamicAgent:%s] Obsługuję akcję '%s'.", self._agent_id, action
        )

        # Zbuduj prompt uwzględniając opis agenta i treść zadania
        task_description = chat_text or action or str(params)
        prompt = (
            f"Jesteś agentem '{self._role}' w grze 'Człowiek Roku'.\n"
            f"Twoja specjalizacja: {self._description}\n\n"
            f"Zadanie: {task_description}"
        )
        result_text = await self._llm.generate(prompt)
        return {
            "status": "ok",
            "agent_id": self._agent_id,
            "role": self._role,
            "action": action,
            "result": result_text,
        }

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
