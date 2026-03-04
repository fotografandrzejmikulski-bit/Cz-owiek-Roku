"""
Agenty potoku Deep Research – inspirowane architekturą LangGraph.

Potok 4-fazowy (Planner → Researcher × N → Critic → Writer):

  Faza 1  Planner   – dekompozycja pytania na pytania pomocnicze + plan
  Faza 2  Researcher – równoległe (asyncio fan-out) przeszukiwanie źródeł
  Faza 3  Critic    – ocena jakości (0-100) + feedback → pętla refleksji
  Faza 4  Writer    – synteza finalnego raportu eksperckiego

Klasa DeepResearchOrchestrator koordynuje cały potok w jednym węźle,
używając dwóch klientów LLM:
  - _llm_planner : potężny model (Gemini Pro / o3) – Planner, Critic, Writer
  - _llm_worker  : szybki model (Gemini Flash / mock) – równoległe Researcher
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, TYPE_CHECKING

from src.agents.base_agent import BaseAgent
from src.communication.llm_client import BaseLlmClient, create_llm_client
from src.communication.search_client import BaseSearchClient, create_search_client
from src.models.message import AgentMessage, MessageType
from src.models.research_state import (
    ResearchFinding,
    ResearchPlan,
    ResearchState,
    ResearchStatus,
)

if TYPE_CHECKING:
    from src.communication.broker import MessageBroker

logger = logging.getLogger(__name__)

# Ile pytań pomocniczych generuje planer (domyślnie)
_DEFAULT_SUB_QUESTIONS = 4


class DeepResearchOrchestrator(BaseAgent):
    """
    Koordynuje 4-fazowy potok Deep Research.

    Architektura (wzorzec Planner-Reflector):
      - Dwuwarstwowy LLM: potężny planista + szybki pracownik
      - Fan-out: N równoległych wątków badawczych (asyncio.gather)
      - Pętla refleksji: powtarza fazy 2-3 aż quality_score >= threshold
      - Postęp w czasie rzeczywistym: publikuje zdarzenia BROADCAST do WebSocket
    """

    def __init__(
        self,
        broker: "MessageBroker",
        llm_planner: BaseLlmClient | None = None,
        llm_worker: BaseLlmClient | None = None,
        search_client: BaseSearchClient | None = None,
    ) -> None:
        super().__init__(
            agent_id="deep_research_orchestrator",
            role="deep_research",
            broker=broker,
        )
        # Planner używa potężnego modelu; Worker używa szybkiego modelu
        self._llm_planner = llm_planner or create_llm_client()
        self._llm_worker = llm_worker or self._llm_planner
        self._search = search_client or create_search_client()

    # ------------------------------------------------------------------
    # Główna metoda – koordynacja potoku
    # ------------------------------------------------------------------

    async def process_task(self, message: AgentMessage) -> dict[str, Any]:
        payload = message.payload
        query = (
            payload.get("query")
            or payload.get("chat_text")
            or payload.get("theme", "")
        )
        state = ResearchState(
            query=query,
            max_iterations=int(payload.get("max_iterations", 3)),
            reflection_threshold=int(payload.get("reflection_threshold", 75)),
        )

        logger.info("[DeepResearch] Startuje badanie: '%s'", query[:80])

        try:
            # ── Faza 1: Planowanie ──────────────────────────────────────
            state.status = ResearchStatus.PLANNING
            await self._broadcast_progress(state)
            state.plan = await self._plan(state)

            # ── Fazy 2-3: Iteracyjne badania + refleksja ────────────────
            for _ in range(state.max_iterations):
                state.status = ResearchStatus.RESEARCHING
                await self._broadcast_progress(state)
                new_findings = await self._research_parallel(state)
                state.findings.extend(new_findings)

                state.status = ResearchStatus.REFLECTING
                await self._broadcast_progress(state)
                critique = await self._critique(state)
                state.quality_score = critique["score"]
                state.feedback = critique["feedback"]
                state.iteration += 1

                logger.info(
                    "[DeepResearch] Iteracja %d – jakość: %d/100 (próg: %d)",
                    state.iteration, state.quality_score, state.reflection_threshold,
                )
                if state.quality_score >= state.reflection_threshold:
                    break

            # ── Faza 4: Synteza raportu ──────────────────────────────────
            state.status = ResearchStatus.WRITING
            await self._broadcast_progress(state)
            state.final_report = await self._write(state)
            state.status = ResearchStatus.DONE

        except Exception as exc:
            state.status = ResearchStatus.ERROR
            state.final_report = f"Błąd podczas badania: {exc}"
            logger.exception("[DeepResearch] Krytyczny błąd: %s", exc)

        result = state.to_dict()
        await self._broadcast_progress(state)
        return result

    # ------------------------------------------------------------------
    # Faza 1: Planner – dekompozycja pytania
    # ------------------------------------------------------------------

    async def _plan(self, state: ResearchState) -> ResearchPlan:
        """Generuje strukturyzowany plan badawczy z pytaniami pomocniczymi."""
        prompt = (
            "Jestes strategicznym planista badan. Zdekomponuj pytanie na "
            f"{_DEFAULT_SUB_QUESTIONS} konkretnych pytan pomocniczych.\n\n"
            f"Pytanie glowne: {state.query}\n\n"
            "Odpowiedz TYLKO w formacie JSON (bez komentarzy):\n"
            '{"sub_questions": ["...", "..."], "source_strategy": "...", '
            '"success_criteria": ["..."]}'
        )
        raw = await self._llm_planner.generate(prompt)
        plan = self._parse_json(raw)

        sub_qs = plan.get("sub_questions") or []
        if not sub_qs:
            sub_qs = [
                state.query,
                f"Kontekst historyczny: {state.query}",
                f"Aktualne dane i statystyki dotyczace: {state.query}",
                f"Praktyczne implikacje i wnioski: {state.query}",
            ]

        return ResearchPlan(
            main_query=state.query,
            sub_questions=sub_qs[:_DEFAULT_SUB_QUESTIONS],
            source_strategy=plan.get("source_strategy", "general"),
            success_criteria=plan.get("success_criteria", []),
        )

    # ------------------------------------------------------------------
    # Faza 2: Researcher – równoległy fan-out
    # ------------------------------------------------------------------

    async def _research_parallel(
        self, state: ResearchState
    ) -> list[ResearchFinding]:
        """Uruchamia N równoległych wątków badawczych (asyncio.gather)."""
        questions = state.plan.sub_questions if state.plan else [state.query]
        feedback_ctx = "\n".join(state.feedback) if state.feedback else ""

        tasks = [
            self._research_single(q, feedback_ctx)
            for q in questions
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        findings = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("[DeepResearch] Wątek badawczy zwrócił błąd: %s", r)
                findings.append(ResearchFinding(
                    sub_question="unknown",
                    summary=f"Blad wątku: {r}",
                    confidence=0.0,
                ))
            else:
                findings.append(r)
        return findings

    async def _research_single(
        self, question: str, feedback_ctx: str
    ) -> ResearchFinding:
        """Przeszukuje jedno pytanie pomocnicze i syntetyzuje wynik."""
        results = await self._search.search(question, max_results=5)

        context = "\n\n".join(
            f"[{r.url}]\n{r.title}\n{r.content[:600]}"
            for r in results
        )
        feedback_part = (
            f"\nUwzglednij wczesniejsze uwagi krytyka:\n{feedback_ctx}"
            if feedback_ctx else ""
        )
        prompt = (
            f"Pytanie badawcze: {question}\n\n"
            f"Wyniki wyszukiwania:\n{context}"
            f"{feedback_part}\n\n"
            "Podaj zwiezle, merytoryczne podsumowanie (3-5 zdan) "
            "z kluczowymi faktami i wnioskami."
        )
        summary = await self._llm_worker.generate(prompt)
        avg_score = (
            sum(r.score for r in results) / len(results) if results else 0.5
        )
        return ResearchFinding(
            sub_question=question,
            summary=summary,
            sources=[r.url for r in results],
            confidence=round(avg_score, 2),
        )

    # ------------------------------------------------------------------
    # Faza 3: Critic – pętla refleksji
    # ------------------------------------------------------------------

    async def _critique(self, state: ResearchState) -> dict[str, Any]:
        """Ocenia jakość badań i generuje feedback dla następnej iteracji."""
        n = len(state.plan.sub_questions) if state.plan else 1
        # Only evaluate findings from the latest iteration
        latest = state.findings[-n:] if len(state.findings) >= n else state.findings

        findings_text = "\n\n".join(
            f"Pytanie: {f.sub_question}\nOdpowiedz: {f.summary}"
            for f in latest
        )
        prompt = (
            "Jestes surowym, obiektywnym recenzentem badan naukowych. "
            "Ocen jakosc ponizszych wynikow (0-100).\n\n"
            f"Pytanie glowne: {state.query}\n\n"
            f"Wyniki badan:\n{findings_text}\n\n"
            "Kryteria oceny: pokrycie tematyczne, rzetelnosc zrodel, "
            "glebokos analizy, logiczna spojnosc.\n\n"
            "Odpowiedz TYLKO w JSON:\n"
            '{"score": <0-100>, "feedback": ["uwaga1", "uwaga2"]}\n\n'
            "score >= 75 = wystarczajaca jakosc. "
            "Ponizej 75: wymien konkretne luki do uzupelnienia."
        )
        raw = await self._llm_planner.generate(prompt)
        data = self._parse_json(raw)

        try:
            score = min(100, max(0, int(data.get("score", 70))))
        except (TypeError, ValueError):
            score = 70

        return {
            "score": score,
            "feedback": data.get("feedback", ["Sprawdz zrodla pierwotne."]),
        }

    # ------------------------------------------------------------------
    # Faza 4: Writer – synteza finalnego raportu
    # ------------------------------------------------------------------

    async def _write(self, state: ResearchState) -> str:
        """Syntetyzuje zebrany materiał w profesjonalny raport ekspercki."""
        findings_md = "\n\n".join(
            f"### {f.sub_question}\n{f.summary}\n"
            f"*Zrodla: {', '.join(f.sources[:3])}*"
            for f in state.findings
        )
        prompt = (
            "Jestes ekspertem w pisaniu raportow analitycznych. "
            "Napisz profesjonalny raport po polsku na podstawie zebranych danych.\n\n"
            f"Pytanie glowne: {state.query}\n\n"
            f"Zebrane badania:\n{findings_md}\n\n"
            f"Jakosc badan: {state.quality_score}/100 "
            f"po {state.iteration} iteracjach refleksji.\n\n"
            "Struktura raportu:\n"
            "1. **Synteza Wykonawcza** (max 150 slow)\n"
            "2. **Analiza Szczegolowa** (sekcje per pytanie)\n"
            "3. **Wnioski Strategiczne** (3-5 punktow)\n"
            "4. **Zrodla** (lista URLi)\n\n"
            "Styl: profesjonalny, ekspercki, bez zbednych przymiotnikow."
        )
        return await self._llm_planner.generate(prompt)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _broadcast_progress(self, state: ResearchState) -> None:
        """Wysyła zdarzenie postępu do wszystkich klientów WebSocket."""
        update = AgentMessage(
            type=MessageType.BROADCAST,
            sender_id=self._agent_id,
            payload={
                "event": "research_progress",
                **state.to_dict(),
            },
        )
        await self._broker.publish(update)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Wyciąga JSON z odpowiedzi modelu (ignoruje otaczający tekst)."""
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except (json.JSONDecodeError, AttributeError):
            pass
        return {}

    def get_capabilities(self) -> list[str]:
        return ["deep_research", "research_planning", "report_synthesis"]
