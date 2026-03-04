"""
Agent Builder – tworzenie własnych agentów przez użytkownika.

Obsługuje trzy tryby:
  - **Pro Code**  : pełna specyfikacja JSON (dla programistów)
  - **No Code**   : formularz z wyboru kategorii/domeny/roli (bez kodu)
  - **Hybrid**    : szablon bazowy + opcjonalne nadpisania kodu

Zbudowane agenty są zapisywane do ``data/custom_agents.json`` i mogą być
uruchamiane przez ``CustomBuiltAgent`` (rozszerzenie DynamicRegistryAgent).
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

_DEFAULT_CUSTOM_AGENTS_PATH = (
    Path(__file__).parent.parent.parent / "data" / "custom_agents.json"
)

BuilderMode = Literal["pro_code", "no_code", "hybrid"]

# ---------------------------------------------------------------------------
# Dataclass: niestandardowy agent
# ---------------------------------------------------------------------------

@dataclass
class CustomAgentSpec:
    """Specyfikacja agenta zbudowanego przez użytkownika."""
    agent_id:        str
    display_name:    str
    domain:          str
    role:            str
    specialization:  str
    mission:         str
    system_prompt:   str
    category:        str
    safety:          str
    builder_mode:    BuilderMode
    created_by:      str        # user email / google sub
    created_at:      str
    custom_code:     str = ""   # opcjonalny kod Python (tryb pro_code/hybrid)
    tools:           list[str] = field(default_factory=list)
    metadata:        dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CustomAgentSpec":
        return cls(
            agent_id       = d["agent_id"],
            display_name   = d["display_name"],
            domain         = d["domain"],
            role           = d["role"],
            specialization = d["specialization"],
            mission        = d["mission"],
            system_prompt  = d["system_prompt"],
            category       = d["category"],
            safety         = d.get("safety", "safe"),
            builder_mode   = d.get("builder_mode", "no_code"),
            created_by     = d.get("created_by", "anonymous"),
            created_at     = d.get("created_at", ""),
            custom_code    = d.get("custom_code", ""),
            tools          = d.get("tools", []),
            metadata       = d.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Persystencja
# ---------------------------------------------------------------------------

class CustomAgentStore:
    """Prosty plik-JSON store dla custom agentów."""

    def __init__(self, path: Path = _DEFAULT_CUSTOM_AGENTS_PATH) -> None:
        self._path = path
        self._agents: dict[str, CustomAgentSpec] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with open(self._path, encoding="utf-8") as fh:
            raw: list[dict] = json.load(fh)
        self._agents = {
            d["agent_id"]: CustomAgentSpec.from_dict(d)
            for d in raw
        }
        logger.info("Załadowano %d custom agentów z %s", len(self._agents), self._path)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(
                [a.to_dict() for a in self._agents.values()],
                fh, ensure_ascii=False, indent=2,
            )

    def add(self, spec: CustomAgentSpec) -> None:
        self._agents[spec.agent_id] = spec
        self._save()

    def get(self, agent_id: str) -> CustomAgentSpec | None:
        return self._agents.get(agent_id)

    def delete(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        self._save()
        return True

    def all(self) -> list[CustomAgentSpec]:
        return list(self._agents.values())

    def count(self) -> int:
        return len(self._agents)

    def page(self, offset: int = 0, limit: int = 100) -> list[CustomAgentSpec]:
        items = self.all()
        return items[offset: offset + limit]


# ---------------------------------------------------------------------------
# Builder: Pro Code
# ---------------------------------------------------------------------------

class ProCodeBuilder:
    """
    Buduje agenta z pełnej specyfikacji JSON dostarczonej przez dewelopera.

    Oczekuje wszystkich pól CustomAgentSpec; system_prompt musi być podany
    jawnie; custom_code jest opcjonalny.
    """

    def build(self, payload: dict[str, Any], created_by: str = "anonymous") -> CustomAgentSpec:
        _validate_pro_code(payload)
        agent_id = f"custom_{uuid.uuid4().hex[:12]}"
        return CustomAgentSpec(
            agent_id      = agent_id,
            display_name  = payload["display_name"],
            domain        = payload["domain"],
            role          = payload["role"],
            specialization= payload["specialization"],
            mission       = payload["mission"],
            system_prompt = payload["system_prompt"],
            category      = payload.get("category", "specialist"),
            safety        = payload.get("safety", "safe"),
            builder_mode  = "pro_code",
            created_by    = created_by,
            created_at    = _now_iso(),
            custom_code   = payload.get("custom_code", ""),
            tools         = payload.get("tools", []),
            metadata      = payload.get("metadata", {}),
        )


def _validate_pro_code(payload: dict[str, Any]) -> None:
    required = ("display_name", "domain", "role", "specialization", "mission", "system_prompt")
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise ValueError(f"Brakujące pola: {missing}")
    if len(payload["system_prompt"]) < 10:
        raise ValueError("system_prompt jest za krótki (min. 10 znaków).")


# ---------------------------------------------------------------------------
# Builder: No Code
# ---------------------------------------------------------------------------

# Dostępne opcje dla formularza
NO_CODE_DOMAINS = [
    "Medycyna", "Prawo", "Finanse", "Edukacja", "Nauka", "Sztuka", "Muzyka",
    "Sport", "Technologia", "Środowisko", "Rolnictwo", "Turystyka",
    "Informatyka", "Robotyka", "Cyberbezpieczeństwo", "Blockchain",
    "Marketing", "Zarządzanie", "Psychologia", "Filozofia", "Historia",
]

NO_CODE_ROLES = [
    "Analityk", "Asystent", "Doradca", "Ekspert", "Edukator",
    "Mentor", "Moderator", "Specjalista", "Strateg", "Zarządca",
    "Trener", "Validator", "Mediator", "Badacz", "Coach",
]

NO_CODE_CATEGORIES = [
    "education", "research", "creative", "scientific",
    "social", "specialist", "blockchain",
]

NO_CODE_SAFETY = ["safe", "monitored", "sandboxed"]


class NoCodeBuilder:
    """
    Buduje agenta z formularza No-Code (pól wyboru).

    system_prompt jest generowany automatycznie na podstawie wyborów.
    """

    def build(
        self,
        display_name: str,
        domain: str,
        role: str,
        specialization: str,
        category: str = "specialist",
        safety: str = "safe",
        created_by: str = "anonymous",
        extra_instructions: str = "",
    ) -> CustomAgentSpec:
        self._validate(domain, role, category, safety)

        system_prompt = self._generate_prompt(role, domain, specialization, extra_instructions)
        mission = f"Wspieranie użytkowników w obszarze {domain} jako {role} ds. {specialization}."

        agent_id = f"custom_{uuid.uuid4().hex[:12]}"
        return CustomAgentSpec(
            agent_id      = agent_id,
            display_name  = display_name,
            domain        = domain,
            role          = role,
            specialization= specialization,
            mission       = mission,
            system_prompt = system_prompt,
            category      = category,
            safety        = safety,
            builder_mode  = "no_code",
            created_by    = created_by,
            created_at    = _now_iso(),
        )

    @staticmethod
    def _validate(domain: str, role: str, category: str, safety: str) -> None:
        if domain not in NO_CODE_DOMAINS:
            raise ValueError(f"Nieznana domena: {domain!r}. Wybierz z: {NO_CODE_DOMAINS}")
        if role not in NO_CODE_ROLES:
            raise ValueError(f"Nieznana rola: {role!r}. Wybierz z: {NO_CODE_ROLES}")
        if category not in NO_CODE_CATEGORIES:
            raise ValueError(f"Nieznana kategoria: {category!r}.")
        if safety not in NO_CODE_SAFETY:
            raise ValueError(f"Nieznany poziom bezpieczeństwa: {safety!r}.")

    @staticmethod
    def _generate_prompt(role: str, domain: str, spec: str, extra: str) -> str:
        base = (
            f"Jesteś {role} specjalizującym się w {spec} w dziedzinie {domain}. "
            f"Twoje odpowiedzi są profesjonalne, precyzyjne i oparte na wiedzy eksperckiej. "
            f"Zawsze pomagasz użytkownikowi w sposób rzetelny i zrozumiały."
        )
        if extra:
            base += f" Dodatkowe instrukcje: {extra}"
        return base

    @staticmethod
    def get_form_options() -> dict[str, list[str]]:
        return {
            "domains":    NO_CODE_DOMAINS,
            "roles":      NO_CODE_ROLES,
            "categories": NO_CODE_CATEGORIES,
            "safety":     NO_CODE_SAFETY,
        }


# ---------------------------------------------------------------------------
# Builder: Hybrid
# ---------------------------------------------------------------------------

class HybridBuilder:
    """
    Łączy No-Code (formularz) z opcjonalnym nadpisaniem system_prompt (Pro Code).

    Deweloper może podać własny system_prompt i/lub custom_code,
    zachowując wygodę formularza dla pozostałych pól.
    """

    def __init__(self) -> None:
        self._no_code = NoCodeBuilder()

    def build(
        self,
        display_name: str,
        domain: str,
        role: str,
        specialization: str,
        category: str = "specialist",
        safety: str = "safe",
        created_by: str = "anonymous",
        # Opcjonalne nadpisania
        system_prompt_override: str = "",
        custom_code: str = "",
        tools: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CustomAgentSpec:
        # Najpierw zbuduj podstawowy agent No-Code
        spec = self._no_code.build(
            display_name  = display_name,
            domain        = domain,
            role          = role,
            specialization= specialization,
            category      = category,
            safety        = safety,
            created_by    = created_by,
        )
        # Nadpisz opcjonalne pola
        override_kwargs: dict[str, Any] = {"builder_mode": "hybrid"}
        if system_prompt_override:
            override_kwargs["system_prompt"] = system_prompt_override
        if custom_code:
            override_kwargs["custom_code"] = custom_code
        if tools:
            override_kwargs["tools"] = tools
        if metadata:
            override_kwargs["metadata"] = metadata

        from dataclasses import replace
        return replace(spec, **override_kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
