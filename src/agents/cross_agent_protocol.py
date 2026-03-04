"""
Cross-Agent Protocol – Protokół Komunikacji Międzyagentowej (§9.1).

Implementuje zintegrowaną architekturę bezpieczeństwa dla ekosystemu
agentów dla Pokolenia Alpha i Z.

Scenariusz z raportu:
  Użytkownik przegrywa serie meczów (Strateg wykrywa Tilt)
  → Bio-Optymizer wykrywa wzrost tętna
  → Skarbnik blokuje impulsywny zakup skina
  → System sugeruje sesję oddechową z Duchowym Kompasem

CrossAgentBus       – magistrala sygnałów między agentami
SafetyCoordinator   – koordynator bezpieczeństwa (eskalacja, rodzic-dashboard)
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from src.models.youth_models import CrossAgentSignal, SafetyLevel

logger = logging.getLogger(__name__)

# Typ callbacku – agent obsługujący sygnał
SignalHandler = Callable[[CrossAgentSignal], None]


class CrossAgentBus:
    """
    Magistrala sygnałów między agentami (publish/subscribe).

    Agenty subskrybują typy sygnałów, które chcą obserwować.
    Sygnały mogą być adresowane do konkretnego agenta lub broadcastowane.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[SignalHandler]] = defaultdict(list)
        self._history: list[CrossAgentSignal] = []

    def subscribe(self, signal_type: str, handler: SignalHandler) -> None:
        """Zarejestruj handler dla danego typu sygnału."""
        self._handlers[signal_type].append(handler)

    def publish(self, signal: CrossAgentSignal) -> int:
        """
        Opublikuj sygnał na magistrali.

        Zwraca liczbę handlerów, które odebrały sygnał.
        """
        self._history.append(signal)
        handlers = self._handlers.get(signal.signal_type, [])

        # Filtrowanie po target_agent (None = broadcast do wszystkich subskrybentów)
        notified = 0
        for handler in handlers:
            try:
                handler(signal)
                notified += 1
            except Exception as exc:
                logger.exception(
                    "[CrossAgentBus] Błąd handlera dla '%s': %s",
                    signal.signal_type, exc,
                )
        logger.info(
            "[CrossAgentBus] Sygnał '%s' od '%s' → %d handlerów.",
            signal.signal_type, signal.source_agent, notified,
        )
        return notified

    def get_signals(
        self,
        signal_type: str | None = None,
        safety_level: SafetyLevel | None = None,
        since: datetime | None = None,
    ) -> list[CrossAgentSignal]:
        """Zwróć filtrowaną historię sygnałów."""
        signals = list(self._history)
        if signal_type:
            signals = [s for s in signals if s.signal_type == signal_type]
        if safety_level:
            signals = [s for s in signals if s.safety_level == safety_level]
        if since:
            signals = [s for s in signals if s.timestamp >= since]
        return signals

    @property
    def history_size(self) -> int:
        return len(self._history)


# ---------------------------------------------------------------------------
# Globalna magistrala (singleton w obrębie procesu)
# ---------------------------------------------------------------------------
_default_bus: CrossAgentBus | None = None


def get_default_bus() -> CrossAgentBus:
    """Zwraca globalną magistralę sygnałów (lazy init)."""
    global _default_bus
    if _default_bus is None:
        _default_bus = CrossAgentBus()
    return _default_bus


# ---------------------------------------------------------------------------
# SafetyCoordinator – koordynator bezpieczeństwa (§9.2, §9.3)
# ---------------------------------------------------------------------------

class SafetyCoordinator:
    """
    Koordynuje odpowiedź systemu na sygnały bezpieczeństwa.

    Priorytety:
    1. RED:    Natychmiastowa interwencja kryzysowa + powiadomienie rodzica.
    2. ORANGE: Aktywne przekierowanie do odpowiedniego agenta wsparcia.
    3. YELLOW: Monitorowanie + łagodne ostrzeżenie dla użytkownika.
    4. GREEN:  Normalny przepływ.

    Implementuje "Dashboard Trendów" dla rodziców (§9.3):
    - Rodzice NIE widzą treści rozmów.
    - Rodzice WIDZĄ anomalie (np. wykryto wzorzec zaburzeń odżywiania).
    """

    # Sygnały, które automatycznie eskalują do poziomu RED
    _AUTO_RED_SIGNALS = frozenset({
        "crisis_detected",          # Hygeia: myśli samobójcze/samookaleczenie
        "eating_disorder_risk",     # Bio-Optymizer: ryzyko zaburzeń odżywiania
        "radicalization_detected",  # Agor: retoryka ekstremistyczna
    })

    # Sygnały mapujące do rekomendowanego agenta wsparcia
    _REDIRECT_MAP: dict[str, str] = {
        "tilt_detected":      "duchowy_kompas",    # Gaming tilt → Duchowy Kompas
        "impulse_purchase":   "skarbnik",           # Impuls zakupowy → Skarbnik
        "stress_elevated":    "duchowy_kompas",     # Stres → medytacja
        "social_overload":    "regulator_energii",  # Przebodźcowanie → Regulator
        "misinformation":     "agor",               # Dezinformacja → Agor
    }

    def __init__(self, bus: CrossAgentBus | None = None) -> None:
        self._bus = bus or get_default_bus()
        self._parent_alerts: list[dict[str, Any]] = []

    def process_signal(self, signal: CrossAgentSignal) -> dict[str, Any]:
        """
        Przetwórz sygnał bezpieczeństwa i zdecyduj o odpowiedzi systemu.

        Zwraca:
            dict z kluczami: action, redirect_to, parent_alert, message
        """
        response: dict[str, Any] = {
            "signal_id":    signal.signal_id,
            "safety_level": signal.safety_level.value,
            "action":       "none",
            "redirect_to":  None,
            "parent_alert": False,
            "message":      "",
        }

        # Automatyczna eskalacja do RED dla krytycznych sygnałów
        if signal.signal_type in self._AUTO_RED_SIGNALS:
            signal.safety_level = SafetyLevel.RED

        if signal.safety_level == SafetyLevel.RED:
            response["action"]       = "crisis_intervention"
            response["parent_alert"] = True  # Jedyny przypadek powiadamiający rodzica
            response["message"]      = (
                "Wykryto sytuację kryzysową. "
                "Skontaktuj się z dorosłym lub zadzwoń pod numer 116 111."
            )
            self._parent_alerts.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type":      signal.signal_type,
                "severity":  "critical",
            })

        elif signal.safety_level == SafetyLevel.ORANGE:
            redirect = self._REDIRECT_MAP.get(signal.signal_type)
            response["action"]      = "redirect"
            response["redirect_to"] = redirect
            response["message"] = (
                f"Wykryto sygnał '{signal.signal_type}'. "
                f"Przekierowuję do agenta {redirect or 'wsparcia'}."
            )

        elif signal.safety_level == SafetyLevel.YELLOW:
            response["action"]  = "warn"
            response["message"] = (
                f"Uwaga: wykryto wzorzec '{signal.signal_type}'. "
                "Monitoruję sytuację."
            )

        logger.info(
            "[SafetyCoordinator] Signal=%s Level=%s Action=%s",
            signal.signal_type,
            signal.safety_level.value,
            response["action"],
        )
        return response

    def get_parent_dashboard(self) -> dict[str, Any]:
        """
        Zwraca "Dashboard Trendów" dla rodzica (§9.3).

        NIE zawiera treści rozmów – tylko anonymizowane anomalie.
        """
        return {
            "total_alerts":    len(self._parent_alerts),
            "critical_alerts": sum(
                1 for a in self._parent_alerts if a.get("severity") == "critical"
            ),
            "recent_alerts":   self._parent_alerts[-5:],  # ostatnie 5 alertów
        }
