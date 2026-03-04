"""
Modele danych dla systemu Egzotycznych/Niszowych Agentów.

Bazuje na "Kompendium Anomalii Agentowych: Taksonomia, Architektura
i Operacjonalizacja Niszowych oraz Ekstrawaganckich Systemów Autonomicznych".

ExoticCategory  – taksonomia kategorii agentów (§1–§7)
ExoticSafety    – poziom ryzyka misalignment / destrukcji
ExoticSession   – stan sesji z egzotycznym agentem
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ExoticCategory(str, Enum):
    """
    Taksonomia kategorii egzotycznych agentów (§1–§7).

    Odpowiada rozdziałom Kompendium Anomalii Agentowych.
    """
    WETWARE       = "wetware"       # §1 – hybrydy biologiczno-cyfrowe
    BLOCKCHAIN    = "blockchain"    # §2 – agenty ekonomiczne / DAO
    MISALIGNED    = "misaligned"    # §3 – agenty destrukcyjne / misaligned
    CREATIVE      = "creative"      # §4 – computational creativity
    ALIFE         = "alife"         # §5 – sztuczne życie / symulacje ewolucji
    SOCIAL        = "social"        # §6 – agenty społeczne i polityczne
    SCIENTIFIC    = "scientific"    # §7 – agenty odkryć naukowych


class ExoticSafety(str, Enum):
    """
    Poziom bezpieczeństwa / ryzyka misalignment agenta.

    Agenty §3 (misaligned) działają wyłącznie w trybie sandboxed –
    nigdy nie generują treści szkodliwych, są "muzeum" wzorców.
    """
    SAFE       = "safe"       # Brak ryzyka – standardowe działanie
    MONITORED  = "monitored"  # Wymaga nadzoru (np. autonomiczne DAO)
    SANDBOXED  = "sandboxed"  # Tylko analiza/symulacja – bez efektów zewn.
    RESTRICTED = "restricted" # Ściśle ograniczone (misaligned §3 – tylko opis)


@dataclass
class ExoticSession:
    """
    Stan sesji z egzotycznym agentem.

    Atrybuty:
        session_id:   Unikalny identyfikator sesji
        agent_id:     Agent obsługujący sesję
        category:     Kategoria taksonomiczna agenta
        safety:       Poziom bezpieczeństwa / ryzyka
        query:        Bieżące zapytanie użytkownika
        history:      Historia wymiany (user/agent)
        metadata:     Dane kontekstowe specyficzne dla agenta
        created_at:   Czas rozpoczęcia sesji
    """
    session_id:  str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id:    str = "unknown"
    category:    ExoticCategory = ExoticCategory.ALIFE
    safety:      ExoticSafety   = ExoticSafety.SAFE
    query:       str = ""
    history:     list[dict[str, str]] = field(default_factory=list)
    metadata:    dict[str, Any] = field(default_factory=dict)
    created_at:  datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def add_exchange(self, user: str, agent: str) -> None:
        self.history.append({"role": "user",  "content": user})
        self.history.append({"role": "agent", "content": agent})

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id":  self.session_id,
            "agent_id":    self.agent_id,
            "category":    self.category.value,
            "safety":      self.safety.value,
            "history_len": len(self.history),
            "created_at":  self.created_at.isoformat(),
        }
