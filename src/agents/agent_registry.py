"""
Rejestr 55 555 unikalnych agentów z wszelkich dziedzin świata.

AgentRegistryEntry  – immutable dataclass opisujący jednego agenta
AgentRegistry       – singleton ładujący rejestr z data/agent_registry.json
DynamicRegistryAgent – instancja agenta zdolna do przetwarzania zadań

Rejestr pokrywa 1300+ domen: nauki przyrodnicze, inżynieryjne, medyczne,
społeczne, humanistyka, sztuka, technologia, prawo, sport, kosmos, energia,
gastronomia, moda, media, zdrowie, filozofia, religia, obronność, transport,
budownictwo, psychologia, nowe technologie, klimat, programowanie, gry AAA,
gry indie, komiksy, książki, ebooki, aplikacje mobilne i wiele innych.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, TYPE_CHECKING

from src.agents.base_agent import BaseAgent
from src.communication.llm_client import BaseLlmClient, create_llm_client
from src.models.message import AgentMessage, MessageType

if TYPE_CHECKING:
    from src.communication.broker import MessageBroker

logger = logging.getLogger(__name__)

# Domyślna ścieżka do pliku rejestru
_DEFAULT_REGISTRY_PATH = Path(__file__).parent.parent.parent / "data" / "agent_registry.json"


# ---------------------------------------------------------------------------
# Dataclass: wpis w rejestrze
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentRegistryEntry:
    """Niezmienny opis agenta z bazy 6666."""
    agent_id:       str
    display_name:   str
    domain:         str
    role:           str
    specialization: str
    mission:        str
    category:       str
    safety:         str
    system_prompt:  str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentRegistryEntry":
        return cls(
            agent_id       = d["agent_id"],
            display_name   = d["display_name"],
            domain         = d["domain"],
            role           = d["role"],
            specialization = d["specialization"],
            mission        = d["mission"],
            category       = d["category"],
            safety         = d["safety"],
            system_prompt  = d["system_prompt"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id":       self.agent_id,
            "display_name":   self.display_name,
            "domain":         self.domain,
            "role":           self.role,
            "specialization": self.specialization,
            "mission":        self.mission,
            "category":       self.category,
            "safety":         self.safety,
        }


# ---------------------------------------------------------------------------
# Singleton rejestr
# ---------------------------------------------------------------------------

class AgentRegistry:
    """
    Rejestr agentów wczytywany z pliku JSON.

    Metody:
        get(agent_id)  → AgentRegistryEntry | None
        all()          → list[AgentRegistryEntry]
        count()        → int
        search(query)  → list[AgentRegistryEntry]
        by_category(c) → list[AgentRegistryEntry]
    """

    def __init__(self, path: Path = _DEFAULT_REGISTRY_PATH) -> None:
        self._path = path
        self._entries: dict[str, AgentRegistryEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("Plik rejestru nie istnieje: %s", self._path)
            return
        with open(self._path, encoding="utf-8") as fh:
            raw: list[dict] = json.load(fh)
        self._entries = {
            d["agent_id"]: AgentRegistryEntry.from_dict(d)
            for d in raw
        }
        logger.info("Załadowano %d agentów z %s", len(self._entries), self._path)

    def get(self, agent_id: str) -> AgentRegistryEntry | None:
        return self._entries.get(agent_id)

    def all(self) -> list[AgentRegistryEntry]:
        return list(self._entries.values())

    def count(self) -> int:
        return len(self._entries)

    def search(
        self,
        query: str,
        limit: int = 50,
    ) -> list[AgentRegistryEntry]:
        """Wyszukiwanie pełnotekstowe w display_name, domain, role, specialization."""
        q = query.lower()
        results = [
            e for e in self._entries.values()
            if (q in e.display_name.lower()
                or q in e.domain.lower()
                or q in e.role.lower()
                or q in e.specialization.lower()
                or q in e.mission.lower())
        ]
        return results[:limit]

    def by_category(self, category: str) -> list[AgentRegistryEntry]:
        return [e for e in self._entries.values() if e.category == category]

    def page(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[AgentRegistryEntry]:
        """Stronicowanie listy agentów."""
        all_entries = self.all()
        return all_entries[offset: offset + limit]


@lru_cache(maxsize=1)
def get_default_registry() -> AgentRegistry:
    """Zwraca singleton rejestru (leniwa inicjalizacja)."""
    return AgentRegistry()


# ---------------------------------------------------------------------------
# DynamicRegistryAgent – agent instancjonowany z wpisu rejestru
# ---------------------------------------------------------------------------

class DynamicRegistryAgent(BaseAgent):
    """
    Agent dynamicznie tworzony na podstawie AgentRegistryEntry.

    Obsługuje przetwarzanie zadań przez LLM z system_prompt z rejestru.
    """

    def __init__(
        self,
        entry: AgentRegistryEntry,
        broker: "MessageBroker",
        llm_client: BaseLlmClient | None = None,
    ) -> None:
        super().__init__(
            agent_id=entry.agent_id,
            role="registry",
            broker=broker,
        )
        self._entry = entry
        self._llm = llm_client or create_llm_client()

    @property
    def display_name(self) -> str:
        return self._entry.display_name

    @property
    def mission(self) -> str:
        return self._entry.mission

    @property
    def category(self) -> str:
        return self._entry.category

    @property
    def safety(self) -> str:
        return self._entry.safety

    def get_capabilities(self) -> list[str]:
        return [
            "registry_agent",
            self.agent_id,
            self._entry.category,
            self._entry.domain,
        ]

    def get_info(self) -> dict[str, Any]:
        return self._entry.to_dict()

    async def process_task(self, message: AgentMessage) -> dict[str, Any]:
        task: str = message.payload.get("task", "").strip()
        prompt = (
            f"{self._entry.system_prompt}\n\n"
            f"Zapytanie: {task}"
        )
        response = await self._llm.generate(prompt)
        return {
            "agent_id":     self.agent_id,
            "display_name": self.display_name,
            "category":     self.category,
            "safety":       self.safety,
            "domain":       self._entry.domain,
            "role":         self._entry.role,
            "specialization": self._entry.specialization,
            "response":     response,
        }
