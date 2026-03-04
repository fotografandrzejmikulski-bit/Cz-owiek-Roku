"""
Wyspecjalizowane agenty gry AAA – Człowiek Roku.

ContentAgent   – generowanie i wzbogacanie treści (opisy, tekstury, poziomy)
NarrativeAgent – tworzenie narracji i dialogów (LLM-based: GPT / Gemini / Mock)
AnalyticsAgent – analiza zachowań gracza i optymalizacja rozgrywki
"""
from __future__ import annotations

import logging
import random
from typing import Any, TYPE_CHECKING

from src.agents.base_agent import BaseAgent
from src.communication.llm_client import BaseLlmClient, create_llm_client
from src.models.message import AgentMessage

if TYPE_CHECKING:
    from src.communication.broker import MessageBroker

logger = logging.getLogger(__name__)


class ContentAgent(BaseAgent):
    """
    Agent odpowiedzialny za generowanie i wzbogacanie zawartości gry:
    opisy przedmiotów, otoczenia, elementów UI.
    Integruje się z modelem LLM (lokalny ONNX lub zdalne API).
    """

    def __init__(self, broker: "MessageBroker") -> None:
        super().__init__(
            agent_id="content_agent",
            role="content",
            broker=broker,
        )

    async def process_task(self, message: AgentMessage) -> dict[str, Any]:
        action = message.payload.get("action", "")
        params = message.payload.get("params", {})
        context = message.payload.get("context", [])
        logger.info("[ContentAgent] Wykonuję akcję '%s'.", action)

        if action == "enrich_content":
            return await self._enrich_content(params, context)
        return {"status": "ok", "action": action, "result": None}

    async def _enrich_content(
        self,
        params: dict[str, Any],
        context: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Wzbogaca wygenerowaną treść o szczegóły wizualne i mechaniczne.
        W produkcji: wywołanie lokalnego modelu ONNX/Llama.cpp.
        """
        narrative_result = next(
            (r for r in context if "story" in r), {}
        )
        story_snippet = narrative_result.get("story", "Nieznana historia")
        enriched = {
            "visual_description": f"Scena oparta na: {story_snippet[:80]}...",
            "difficulty_modifier": round(random.uniform(0.8, 1.5), 2),
            "loot_table": ["zbroja", "miecz", "mikstura"],
        }
        return {"status": "ok", "action": "enrich_content", "result": enriched}

    def get_capabilities(self) -> list[str]:
        return ["content", "enrichment", "loot_generation"]


class NarrativeAgent(BaseAgent):
    """
    Agent narracyjny tworzący opowieści, dialogi i wątki fabularne.
    Korzysta z modeli LLM: OpenAI GPT, Google Gemini lub Mock.
    Backend wybierany przez zmienną środowiskową LLM_BACKEND.
    """

    def __init__(
        self,
        broker: "MessageBroker",
        llm_client: BaseLlmClient | None = None,
    ) -> None:
        super().__init__(
            agent_id="narrative_agent",
            role="narrative",
            broker=broker,
        )
        self._llm = llm_client or create_llm_client()

    async def process_task(self, message: AgentMessage) -> dict[str, Any]:
        action = message.payload.get("action", "")
        params = message.payload.get("params", {})
        logger.info("[NarrativeAgent] Wykonuję akcję '%s'.", action)

        if action == "generate_story":
            return await self._generate_story(params)
        return {"status": "ok", "action": action, "result": None}

    async def _generate_story(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generuje fragment narracji przez wybrany backend LLM.
        W trybie mock: deterministyczna odpowiedź.
        W trybie openai/gemini: wywołanie modelu językowego.
        """
        theme = params.get("theme", "przygoda")
        prompt = (
            f"Napisz krótki (3-4 zdania) dramatyczny fragment historii "
            f"do gry RPG na temat: {theme}."
        )
        story = await self._llm.generate(prompt)
        return {"status": "ok", "action": "generate_story", "story": story}

    def get_capabilities(self) -> list[str]:
        return ["narrative", "dialogue_generation", "quest_design"]


class AnalyticsAgent(BaseAgent):
    """
    Agent analityczny monitorujący zachowania gracza.
    Dostarcza dane do optymalizacji trudności i personalizacji.
    """

    def __init__(self, broker: "MessageBroker") -> None:
        super().__init__(
            agent_id="analytics_agent",
            role="analytics",
            broker=broker,
        )

    async def process_task(self, message: AgentMessage) -> dict[str, Any]:
        action = message.payload.get("action", "")
        params = message.payload.get("params", {})
        logger.info("[AnalyticsAgent] Wykonuję akcję '%s'.", action)

        if action == "analyze":
            return await self._analyze(params)
        return {"status": "ok", "action": action, "result": None}

    async def _analyze(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Analizuje sesję gracza i generuje rekomendacje.
        W produkcji: modele ML (scikit-learn / TorchScript).
        """
        session_data = params.get("session_data", {})
        player_level = session_data.get("player_level", 1)
        score = session_data.get("score", 0)
        engagement_score = min(100, score // max(player_level, 1))
        recommendation = (
            "Zwiększ trudność o 10%"
            if engagement_score > 75
            else "Zaproponuj hint systemowy"
        )
        return {
            "status": "ok",
            "action": "analyze",
            "result": {
                "engagement_score": engagement_score,
                "recommendation": recommendation,
                "churn_risk": engagement_score < 30,
            },
        }

    def get_capabilities(self) -> list[str]:
        return ["analytics", "player_behavior", "difficulty_tuning"]
