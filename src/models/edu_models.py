"""
Modele danych dla systemu Autonomicznych Agentów Korepetytorów (AAK).

EduSession    – stan bieżącej sesji edukacyjnej ucznia
EduLevel      – poziom realizacji przedmiotu
SubjectDomain – dziedziny przedmiotowe
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EduLevel(str, Enum):
    """Poziom realizacji przedmiotu – zgodny z podstawą programową MEN."""
    PODSTAWOWY   = "podstawowy"    # zakres podstawowy
    ROZSZERZONY  = "rozszerzony"   # zakres rozszerzony
    UNKNOWN      = "nieznany"      # do ustalenia przez agenta


class SubjectDomain(str, Enum):
    """Dziedziny dydaktyczne pokryte przez system AAK."""
    HUMANISTYCZNA   = "humanistyczna"       # j. polski, filozofia, sztuka
    HISTORYCZNO_SPOLECZNA = "historyczno_spoleczna"  # historia, WOS, biznes
    STEM_SCIENCES   = "stem_sciences"       # mat., fiz., informatyka
    LIFE_SCIENCES   = "life_sciences"       # biologia, chemia, geografia
    JEZYKI_OBCE     = "jezyki_obce"         # angielski, niemiecki, etc.
    DOBROSTAN       = "dobrostan"           # zdrowie, etyka, WF teoria


@dataclass
class EduSession:
    """
    Stan sesji edukacyjnej – wspólny obiekt stanu przekazywany przez agenta.

    Atrybuty:
        session_id:    Unikalny identyfikator sesji
        agent_id:      Identyfikator agenta (np. "euler_edu")
        subject:       Pełna nazwa przedmiotu (np. "Matematyka")
        domain:        Dziedzina dydaktyczna
        level:         Poziom (podstawowy / rozszerzony)
        student_query: Bieżące pytanie ucznia
        history:       Historia wymiany (role: "student" | "agent")
        metadata:      Dodatkowe dane (np. wyniki diagnostyczne)
        created_at:    Czas rozpoczecia sesji
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = "unknown"
    subject: str = "Nieznany"
    domain: SubjectDomain = SubjectDomain.HUMANISTYCZNA
    level: EduLevel = EduLevel.UNKNOWN
    student_query: str = ""
    history: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def add_exchange(self, student: str, agent: str) -> None:
        """Dodaj wymianę student↔agent do historii."""
        self.history.append({"role": "student", "content": student})
        self.history.append({"role": "agent",   "content": agent})

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id":    self.session_id,
            "agent_id":      self.agent_id,
            "subject":       self.subject,
            "domain":        self.domain.value,
            "level":         self.level.value,
            "student_query": self.student_query,
            "history_len":   len(self.history),
            "created_at":    self.created_at.isoformat(),
        }
