"""
Modele strukturalne Persony Agenta i Procedur Operacyjnych (SOP).

Oparte na §9 raportu "Ekosystem Autonomicznych Agentów AI w Inżynierii
Systemowej i Procesach Kreatywnych (2025-2026)".

AgentPersona  – pełna definicja tożsamości agenta (rola, cele, ograniczenia)
FlowStep      – krok w procedurze operacyjnej
AgentSOP      – Standard Operating Procedure (sekwencja kroków z pętlami zwrotnymi)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolAccess(str, Enum):
    """Poziom dostępu agenta do narzędzi systemowych."""
    NONE         = "none"           # brak dostępu
    READ_ONLY    = "read_only"      # tylko odczyt plików
    READ_WRITE   = "read_write"     # odczyt i zapis
    FULL_SHELL   = "full_shell"     # pełny terminal (ryzykowne)
    SANDBOXED    = "sandboxed"      # kontener / VM


@dataclass
class FlowStep:
    """
    Pojedynczy krok w procedurze operacyjnej agenta.

    Atrybuty:
        name:        Nazwa kroku (np. "Planning", "Generation")
        description: Co agent robi w tym kroku
        on_failure:  Nazwa kroku, do którego wrócić przy błędzie (pętla zwrotna)
        tools:       Narzędzia dostępne w tym kroku
    """
    name:        str
    description: str
    on_failure:  str | None = None    # None = zakończ z błędem
    tools:       list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name":        self.name,
            "description": self.description,
            "on_failure":  self.on_failure,
            "tools":       self.tools,
        }


@dataclass
class AgentSOP:
    """
    Standard Operating Procedure – deterministyczny graf przepływu agenta.

    Wzorzec: Planowanie → Generacja → Krytyka → Poprawa → Akceptacja
    (z konfigurowalnymi pętlami zwrotnymi między krokami).
    """
    name:        str
    description: str
    steps:       list[FlowStep] = field(default_factory=list)

    def step_names(self) -> list[str]:
        return [s.name for s in self.steps]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name":        self.name,
            "description": self.description,
            "steps":       [s.to_dict() for s in self.steps],
        }


@dataclass
class AgentPersona:
    """
    Pełna definicja tożsamości agenta – kluczowy artefakt Architekta Systemów.

    Zawiera:
        agent_id:     Unikalny identyfikator (musi być snake_case)
        display_name: Czytelna nazwa (np. "Inżynier Jądra Rust")
        domain:       Dziedzina (np. "systems_engineering", "gamedev")
        goals:        Lista konkretnych celów (co agent ma osiągnąć)
        constraints:  Lista ograniczeń (czego agent nie robi)
        tool_access:  Poziom dostępu do narzędzi systemowych
        context_window: Maks. rozmiar kontekstu w tokenach
        sop:          Procedura operacyjna (opcjonalna)
        metadata:     Dodatkowe metadane (wersja, autor, etc.)
    """
    agent_id:       str
    display_name:   str
    domain:         str
    goals:          list[str]        = field(default_factory=list)
    constraints:    list[str]        = field(default_factory=list)
    tool_access:    ToolAccess       = ToolAccess.READ_ONLY
    context_window: int              = 128_000
    sop:            AgentSOP | None  = None
    metadata:       dict[str, Any]   = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id":       self.agent_id,
            "display_name":   self.display_name,
            "domain":         self.domain,
            "goals":          self.goals,
            "constraints":    self.constraints,
            "tool_access":    self.tool_access.value,
            "context_window": self.context_window,
            "sop":            self.sop.to_dict() if self.sop else None,
            "metadata":       self.metadata,
        }


# ---------------------------------------------------------------------------
# Predefiniowane SOPy dla agentów specjalistycznych
# ---------------------------------------------------------------------------

#: SOP dla agenta inżynierii systemowej (§2 raportu)
SYSTEMS_SOP = AgentSOP(
    name="KernelEngineerSOP",
    description="Procedura migracji/tworzenia komponentów systemu operacyjnego",
    steps=[
        FlowStep(
            name="Analysis",
            description="Przeanalizuj kod źródłowy. Zidentyfikuj wskaźniki, blokady, "
                        "interakcje ze sprzętem.",
            tools=["read_file", "grep"],
        ),
        FlowStep(
            name="SafetyMapping",
            description="Zaproponuj bezpieczne abstrakcje (Box, Arc, Mutex). "
                        "Użyj unsafe tylko przy rejestrach sprzętowych.",
            on_failure="Analysis",
        ),
        FlowStep(
            name="Generation",
            description="Napisz kod Rust/C++ z pełną dokumentacją // SAFETY:...",
            tools=["write_file"],
            on_failure="SafetyMapping",
        ),
        FlowStep(
            name="Verification",
            description="Stwórz testy jednostkowe i FFI. Propaguj błędy przez Result.",
            tools=["run_tests"],
            on_failure="Generation",
        ),
    ],
)

#: SOP dla agenta literackiego (§4 raportu)
LITERARY_SOP = AgentSOP(
    name="NovelWriterSOP",
    description="Procedura pisania długich form literackich (Writer's Room)",
    steps=[
        FlowStep(
            name="WorldBuilding",
            description="Stwórz 'Biblię Świata': zarysy fabuły, profile postaci, zasady "
                        "świata. Zapisz do bazy wiedzy.",
            tools=["knowledge_base_write"],
        ),
        FlowStep(
            name="Outlining",
            description="Zaplanuj strukturę rozdziałów. Każdy rozdział = krótki opis sceny.",
        ),
        FlowStep(
            name="ChapterWriting",
            description="Pisz każdą scenę używając tylko relevantnych fragmentów z "
                        "bazy wiedzy. Styl: show, don't tell.",
            tools=["knowledge_base_read"],
            on_failure="Outlining",
        ),
        FlowStep(
            name="ContinuityCheck",
            description="Sprawdź spójność z Biblią Świata (np. czy ranny bohater nadal "
                        "jest ranny). Wróć do ChapterWriting jeśli błąd.",
            tools=["knowledge_base_read"],
            on_failure="ChapterWriting",
        ),
        FlowStep(
            name="ProsePolishing",
            description="Popraw styl: eliminuj powtórzenia, AI-izmy, wzmocnij dialogi.",
            on_failure="ChapterWriting",
        ),
    ],
)

#: SOP dla agenta GameDev – Unreal/Unity (§3 raportu)
GAMEDEV_SOP = AgentSOP(
    name="GameDevSOP",
    description="Procedura tworzenia komponentów gry (Unreal/Unity)",
    steps=[
        FlowStep(
            name="Requirements",
            description="Przeanalizuj wymagania. Określ engine, język (C#/C++/Blueprint), "
                        "dziedziczenie klasy.",
        ),
        FlowStep(
            name="ArchitectureDesign",
            description="Zaprojektuj diagram klas, komponenty, interfejsy. "
                        "Dla Unreal: uwzględnij makra UPROPERTY/UFUNCTION.",
        ),
        FlowStep(
            name="CodeGeneration",
            description="Wygeneruj pliki .h i .cpp / .cs. Stosuj konwencje silnika.",
            tools=["write_file"],
            on_failure="ArchitectureDesign",
        ),
        FlowStep(
            name="BugFixing",
            description="Przeanalizuj błędy kompilacji/runtime. Zaproponuj PR z poprawką.",
            tools=["run_tests", "read_file"],
            on_failure="CodeGeneration",
        ),
    ],
)

#: SOP dla agenta webdevelopmentu – MetaGPT-inspired (§8 raportu)
WEBDEV_SOP = AgentSOP(
    name="WebDevSOP",
    description="Procedura tworzenia aplikacji webowych (Full-Stack, MetaGPT-style)",
    steps=[
        FlowStep(
            name="PRD",
            description="PM Agent: Stwórz dokument wymagań produktowych (PRD).",
        ),
        FlowStep(
            name="Architecture",
            description="Architect Agent: Diagram klas, struktura plików, schemat API.",
        ),
        FlowStep(
            name="Implementation",
            description="Engineer Agent: Zaimplementuj backend (FastAPI/Node) + "
                        "frontend (React/Vue) + baza danych.",
            tools=["write_file"],
            on_failure="Architecture",
        ),
        FlowStep(
            name="QA",
            description="QA Agent: Sprawdź kod, napisz testy, zweryfikuj bezpieczeństwo.",
            tools=["run_tests"],
            on_failure="Implementation",
        ),
    ],
)
