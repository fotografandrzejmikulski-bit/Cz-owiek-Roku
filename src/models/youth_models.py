"""
Modele danych dla systemu Agentów Pokolenia Alpha i Z.

Bazuje na §1-§9 raportu "Rozszerzona Architektura Ekosystemu Agentów AI
dla Pokolenia Alpha i Z (2026–2030)".

AgeGroup        – przedziały wiekowe z dostosowanymi regułami bezpieczeństwa
SafetyLevel     – poziom interwencji bezpieczeństwa
CrossAgentSignal – sygnał wymieniany między agentami (Cross-Agent Protocol)
YouthSession    – stan sesji z agentem dla młodzieży
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgeGroup(str, Enum):
    """Przedział wiekowy – determinuje blokady treści i styl komunikacji."""
    PRETEEN   = "preteen"    # 10–12 lat – najbardziej restrykcyjne
    TEEN      = "teen"       # 13–17 lat – standardowe (COPPA, RODO)
    YOUNG_ADULT = "young_adult"  # 18–24 lata – ograniczone blokady dorosłych


class SafetyLevel(str, Enum):
    """Poziom sygnału bezpieczeństwa – steruje eskalacją inter-agentową."""
    GREEN   = "green"    # Brak zagrożeń
    YELLOW  = "yellow"   # Monitorowanie – łagodne ostrzeżenie
    ORANGE  = "orange"   # Interwencja – aktywne przekierowanie
    RED     = "red"      # Kryzys – natychmiastowe działanie + powiadomienie rodzica


@dataclass
class CrossAgentSignal:
    """
    Sygnał wymieniany między agentami przez Cross-Agent Protocol (§9.1).

    Agenty nie działają w silosach: wykryty stres przez Bio-Optymizer
    może blokować transakcję w Skarbniku lub uruchomić sesję w Duchowym Kompasie.

    Atrybuty:
        signal_id:    Unikalny identyfikator sygnału
        source_agent: Agent, który wygenerował sygnał
        target_agent: Agent, do którego jest skierowany (None = broadcast)
        signal_type:  Typ sygnału (np. "tilt_detected", "impulse_purchase")
        safety_level: Poziom zagrożenia
        payload:      Dane kontekstowe (np. {"heart_rate": 110})
        timestamp:    Czas wygenerowania
    """
    source_agent: str
    signal_type:  str
    safety_level: SafetyLevel = SafetyLevel.GREEN
    target_agent: str | None  = None
    payload:      dict[str, Any] = field(default_factory=dict)
    signal_id:    str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:    datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id":    self.signal_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "signal_type":  self.signal_type,
            "safety_level": self.safety_level.value,
            "payload":      self.payload,
            "timestamp":    self.timestamp.isoformat(),
        }


@dataclass
class YouthSession:
    """
    Stan sesji z agentem dla użytkownika z grupy Alpha/Z.

    Atrybuty:
        session_id:     Unikalny identyfikator sesji
        agent_id:       Agent obsługujący sesję
        age_group:      Przedział wiekowy użytkownika
        query:          Bieżące zapytanie użytkownika
        history:        Historia rozmowy
        safety_level:   Aktualny poziom bezpieczeństwa
        cross_signals:  Sygnały wysłane do innych agentów w tej sesji
        metadata:       Dodatkowe dane (np. dane biometryczne, transakcje)
        created_at:     Czas rozpoczęcia sesji
    """
    session_id:   str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id:     str = "unknown"
    age_group:    AgeGroup = AgeGroup.TEEN
    query:        str = ""
    history:      list[dict[str, str]] = field(default_factory=list)
    safety_level: SafetyLevel = SafetyLevel.GREEN
    cross_signals: list[CrossAgentSignal] = field(default_factory=list)
    metadata:     dict[str, Any] = field(default_factory=dict)
    created_at:   datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def add_exchange(self, user: str, agent: str) -> None:
        self.history.append({"role": "user",  "content": user})
        self.history.append({"role": "agent", "content": agent})

    def add_cross_signal(self, signal: CrossAgentSignal) -> None:
        self.cross_signals.append(signal)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id":    self.session_id,
            "agent_id":      self.agent_id,
            "age_group":     self.age_group.value,
            "safety_level":  self.safety_level.value,
            "history_len":   len(self.history),
            "cross_signals": len(self.cross_signals),
            "created_at":    self.created_at.isoformat(),
        }
