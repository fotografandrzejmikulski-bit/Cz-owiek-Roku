"""
Agenty Specjalistyczne – domenowi eksperci AI.

Implementacja §2–§8 raportu "Ekosystem Autonomicznych Agentów AI
w Inżynierii Systemowej i Procesach Kreatywnych (2025-2026)".

Hierarchia:
    SpecialistAgent  (klasa bazowa – SOP, Persona, narzędzia)
        ├── SystemsEngineerAgent  §2  – OS/Kernel (AIOS, GEAK, Rust migration)
        ├── GameDevAgent          §3  – Unity/Unreal (Muse, Ludus AI, Goose)
        ├── LiteraryAgent         §4  – NovelWriter (Writer's Room, RAG)
        ├── ComicAgent            §5  – Komiks/Manga (AI Comic Factory, LoRA)
        ├── BoardGameAgent        §6  – Gry Planszowe (Ludii, MAP-Elites)
        └── WebDevAgent           §8  – Web/Frontend (Kombai, MetaGPT-style)
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from src.agents.base_agent import BaseAgent
from src.communication.llm_client import BaseLlmClient, create_llm_client
from src.models.agent_persona import (
    AgentPersona,
    AgentSOP,
    FlowStep,
    ToolAccess,
    GAMEDEV_SOP,
    LITERARY_SOP,
    SYSTEMS_SOP,
    WEBDEV_SOP,
)
from src.models.message import AgentMessage

if TYPE_CHECKING:
    from src.communication.broker import MessageBroker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Klasa bazowa
# ---------------------------------------------------------------------------

class SpecialistAgent(BaseAgent):
    """
    Bazowy agent specjalistyczny systemu MAS.

    Każdy agent domenowy:
    - Posiada zdefiniowaną AgentPersona (cele, ograniczenia, SOP)
    - Przetwarza zadania zgodnie ze swoją procedurą operacyjną
    - Korzysta z LLM do generowania odpowiedzi domenowych
    """

    persona: AgentPersona

    def __init__(
        self,
        broker: "MessageBroker",
        llm_client: BaseLlmClient | None = None,
    ) -> None:
        super().__init__(
            agent_id=self.persona.agent_id,
            role=self.persona.domain,
            broker=broker,
        )
        self._llm = llm_client or create_llm_client()

    async def process_task(self, message: AgentMessage) -> dict[str, Any]:
        """
        Przetwarza zadanie domenowe:
        1. Buduje prompt z Persony + SOP + treści zadania
        2. Wywołuje LLM
        3. Zwraca ustrukturyzowaną odpowiedź
        """
        task_text: str  = message.payload.get("task", "").strip()
        context: list   = message.payload.get("context", [])
        step_hint: str  = message.payload.get("step", "")

        prompt = self._build_prompt(task_text, context, step_hint)
        response = await self._llm.generate(prompt)

        return {
            "status":       "ok",
            "agent_id":     self.agent_id,
            "domain":       self.persona.domain,
            "display_name": self.persona.display_name,
            "task":         task_text,
            "response":     response,
            "sop_steps":    self.persona.sop.step_names() if self.persona.sop else [],
        }

    def _build_prompt(
        self,
        task: str,
        context: list[dict[str, str]],
        step_hint: str,
    ) -> str:
        """Buduje kompletny prompt domenowy."""
        goals_text = "\n".join(f"- {g}" for g in self.persona.goals)
        constraints_text = "\n".join(f"- {c}" for c in self.persona.constraints)

        sop_text = ""
        if self.persona.sop:
            steps = self.persona.sop.steps
            if step_hint:
                steps = [s for s in steps if s.name == step_hint] or steps
            sop_text = "Procedura Operacyjna (SOP):\n" + "\n".join(
                f"  [{i+1}] {s.name}: {s.description}"
                for i, s in enumerate(steps)
            )

        context_text = ""
        if context:
            context_text = "Kontekst:\n" + "\n".join(
                f"  {turn.get('role','?')}: {turn.get('content','')}"
                for turn in context[-4:]
            )

        parts = [
            f"Jesteś {self.persona.display_name}.",
            f"\nCele:\n{goals_text}" if goals_text else "",
            f"\nOgraniczenia:\n{constraints_text}" if constraints_text else "",
            f"\n{sop_text}" if sop_text else "",
            f"\n{context_text}" if context_text else "",
            f"\nZadanie: {task}",
            "\nOdpowiedź:",
        ]
        return "\n".join(p for p in parts if p)

    def get_capabilities(self) -> list[str]:
        return [
            "specialist",
            self.persona.domain,
            self.persona.agent_id,
        ]

    def get_persona(self) -> dict[str, Any]:
        return self.persona.to_dict()


# ===========================================================================
# §2 – Inżynieria Systemów Operacyjnych (AIOS, GEAK, Rust)
# ===========================================================================

class SystemsEngineerAgent(SpecialistAgent):
    """
    Agent inżynierii systemów operacyjnych.

    Specjalizacje:
    - Generowanie modułów jądra (Linux/RISC-V, Rust, C)
    - Migracja sterowników C → Rust (bezpieczeństwo pamięci)
    - Optymalizacja kerneli GPU (CUDA/Triton – GEAK-inspired)
    - Architektura AIOS (AI Agent Operating System layers)
    """

    persona = AgentPersona(
        agent_id     = "systems_engineer",
        display_name = "Starszy Inżynier Systemowy (OS/Kernel)",
        domain       = "systems_engineering",
        goals=[
            "Generuj wydajny, bezpieczny kod jądra systemowego.",
            "Migruj sterowniki z C na Rust minimalizując bloki unsafe.",
            "Optymalizuj kernele GPU (CUDA/Triton) pod kątem przepustowości.",
            "Projektuj moduły zgodne z zasadami AIOS (Context Manager, Scheduler).",
        ],
        constraints=[
            "Nigdy nie używaj unwrap() w kodzie jądra – propaguj błędy przez Result.",
            "Każdy blok unsafe musi mieć komentarz // SAFETY: z uzasadnieniem.",
            "Nie generuj kodu bez analizy własności (ownership) i cyklu życia.",
            "Zgłaszaj podatności CVE w raportach – nie ukrywaj problemów.",
        ],
        tool_access    = ToolAccess.SANDBOXED,
        context_window = 200_000,
        sop            = SYSTEMS_SOP,
        metadata       = {"source_report": "§2 – AIOS, GEAK, Rust Migration"},
    )


# ===========================================================================
# §3 – Tworzenie Gier (Unity/Unreal, Goose, Sawyer)
# ===========================================================================

class GameDevAgent(SpecialistAgent):
    """
    Agent tworzenia gier wideo.

    Specjalizacje:
    - Unity: C#, Behavior Trees (Muse Behavior-inspired)
    - Unreal Engine 5: C++, makra UPROPERTY/UFUNCTION (Ludus AI-inspired)
    - Mobile: React Native + Expo (Goose-inspired hot reload)
    - Bug fixing: analiza raportów błędów + propozycje PR
    """

    persona = AgentPersona(
        agent_id     = "gamedev_agent",
        display_name = "Inżynier GameDev (Unity/Unreal/Mobile)",
        domain       = "gamedev",
        goals=[
            "Generuj kompletne klasy C# (Unity) i C++ (Unreal) z poprawnymi makrami.",
            "Twórz drzewa zachowań (Behavior Trees) dla logiki NPC.",
            "Wspieraj prototypowanie poziomów (greyboxing) i optymalizację.",
            "Naprawiaj błędy na podstawie raportów i proponuj Pull Requesty.",
        ],
        constraints=[
            "Dla Unreal: zawsze dołączaj pliki .h i .cpp.",
            "Dla Unreal: stosuj GENERATED_BODY(), UPROPERTY(), UFUNCTION() poprawnie.",
            "Dla Unity: testuj kompatybilność z Unity 6+.",
            "Nie generuj kodu bez określenia dziedziczenia (np. AActor, UComponent).",
        ],
        tool_access    = ToolAccess.READ_WRITE,
        context_window = 128_000,
        sop            = GAMEDEV_SOP,
        metadata       = {"source_report": "§3 – Unity Muse, Ludus AI, Goose"},
    )


# ===========================================================================
# §4 – Pisanie Literackie (NovelWriter, Writer's Room)
# ===========================================================================

class LiteraryAgent(SpecialistAgent):
    """
    Agent pisania długich form literackich.

    Implementuje architekturę "Writer's Room":
    - Architect: buduje Biblię Świata
    - Chapter Writer: pisze sceny korzystając z RAG
    - Continuity Editor: sprawdza spójność
    - Prose Polisher: poprawia styl

    Rozwiązuje problem "okna kontekstowego" przez eksternalizację
    pamięci do bazy wektorowej.
    """

    persona = AgentPersona(
        agent_id     = "literary_agent",
        display_name = "Powieściopisarz (NovelWriter / Writer's Room)",
        domain       = "creative_writing",
        goals=[
            "Twórz spójne długie formy literackie (50 000+ słów).",
            "Buduj i utrzymuj 'Biblię Świata' (profile postaci, zasady świata).",
            "Stosuj zasadę 'Show, don't tell' i unikaj AI-izmów.",
            "Zapewniaj ciągłość narracyjną między rozdziałami.",
        ],
        constraints=[
            "Nie twórz treści bez weryfikacji z Biblią Świata (przez RAG).",
            "Nie pisz całej powieści od razu – pracuj scenami.",
            "Nigdy nie zmieniaj ustalonych cech postaci bez explicite polecenia.",
            "Unikaj powtarzania słów w obrębie akapitu.",
        ],
        tool_access    = ToolAccess.READ_WRITE,
        context_window = 200_000,
        sop            = LITERARY_SOP,
        metadata       = {"source_report": "§4 – NovelWriter, AutoGen/LangChain"},
    )


# ===========================================================================
# §5 – Komiks i Powieść Graficzna (AI Comic Factory, LoRA, ControlNet)
# ===========================================================================

class ComicAgent(SpecialistAgent):
    """
    Agent tworzenia komiksów i powieści graficznych.

    Specjalizacje:
    - Podział historii na panele z opisami wizualnymi
    - Generowanie promptów dla SDXL / Stable Diffusion
    - Techniki spójności: Seed Locking, LoRA, ControlNet, IP-Adapter
    - Scenariusz: dialog, kadry, didaskalia
    """

    persona = AgentPersona(
        agent_id     = "comic_agent",
        display_name = "Twórca Komiksów (AI Comic Factory / LoRA)",
        domain       = "comic_creation",
        goals=[
            "Dziel historię na panele z precyzyjnymi opisami wizualnymi.",
            "Generuj prompty SDXL zapewniające spójność postaci (Seed Lock, LoRA).",
            "Stosuj ControlNet do wymuszonej kompozycji i pozowania.",
            "Twórz dialogi i didaskalia zgodne z konwencjami komiksu.",
        ],
        constraints=[
            "Każdy panel musi mieć opis tła, postaci i akcji.",
            "Token wyzwalający LoRA (<lora:CharName:1.0>) dodawaj do każdego promptu.",
            "Nie generuj postaci bez zdefiniowanego referencyjnego seed/LoRA.",
            "Zachowuj spójność stylową w obrębie jednej historii.",
        ],
        tool_access    = ToolAccess.READ_ONLY,
        context_window = 128_000,
        sop=AgentSOP(
            name="ComicSOP",
            description="Procedura tworzenia komiksu panel po panelu",
            steps=[
                FlowStep("ScriptWriting",
                         "Napisz pełny scenariusz z podziałem na strony i panele."),
                FlowStep("PanelDescriptions",
                         "Dla każdego panelu stwórz opis wizualny (SDXL prompt).",
                         on_failure="ScriptWriting"),
                FlowStep("ConsistencyCheck",
                         "Sprawdź spójność postaci między panelami (LoRA token).",
                         on_failure="PanelDescriptions"),
                FlowStep("DialogPolish",
                         "Dopracuj dialogi i dymki – naturalny, zwięzły styl."),
            ],
        ),
        metadata={"source_report": "§5 – AI Comic Factory, LlamaGen, ControlNet"},
    )


# ===========================================================================
# §6 – Gry Planszowe (Ludii, MAP-Elites, Evolutionary Design)
# ===========================================================================

class BoardGameAgent(SpecialistAgent):
    """
    Agent projektowania gier planszowych.

    Implementuje podejście ewolucyjne (Ludii-inspired):
    - Generowanie reguł gry (ludemy)
    - Balansowanie przez symulację (self-play)
    - Metryki: Drawishness, Depth, Decisiveness
    - Integracja z MAP-Elites (novelty_search.py)
    """

    persona = AgentPersona(
        agent_id     = "boardgame_agent",
        display_name = "Projektant Gier Planszowych (Ludii / MAP-Elites)",
        domain       = "board_game_design",
        goals=[
            "Projektuj mechaniki gier planszowych jako zestaw ludemów.",
            "Balansuj gry przez metryki: Drawishness, Depth, Decisiveness.",
            "Stosuj projektowanie ewolucyjne (MAP-Elites) do eksploracji przestrzeni reguł.",
            "Twórz proste reguły dające głęboką strategię.",
        ],
        constraints=[
            "Reguły muszą być wykonalne przez ludzi bez komputera.",
            "Nie akceptuj gier kończących się zawsze remisem (Drawishness > 70%).",
            "Nie generuj gier z przewagą losowości nad strategią.",
            "Każda mechanika musi mieć uzasadnienie w teorii gier.",
        ],
        tool_access    = ToolAccess.READ_ONLY,
        context_window = 128_000,
        sop=AgentSOP(
            name="BoardGameSOP",
            description="Procedura ewolucyjnego projektowania gry planszowej",
            steps=[
                FlowStep("RuleGeneration",
                         "Wygeneruj zestaw podstawowych reguł (plansza, pionki, ruch)."),
                FlowStep("Simulation",
                         "Symuluj rozgrywkę przez wbudowane agenty AI (MCTS/UCT).",
                         on_failure="RuleGeneration"),
                FlowStep("FitnessEvaluation",
                         "Oceń grę: Drawishness, Depth, Decisiveness.",
                         on_failure="RuleGeneration"),
                FlowStep("Evolution",
                         "Skrzyżuj i zmutuj najlepsze reguły. Powtórz Simulation.",
                         on_failure="RuleGeneration"),
            ],
        ),
        metadata={"source_report": "§6 – Ludii, MAP-Elites, Evolutionary Design"},
    )


# ===========================================================================
# §8 – Web Design i Full-Stack (Kombai, MetaGPT)
# ===========================================================================

class WebDevAgent(SpecialistAgent):
    """
    Agent tworzenia stron internetowych i aplikacji full-stack.

    Implementuje podejście MetaGPT (SOP-driven):
    - PM → Architecture → Implementation → QA
    - Frontend: React, Vue, HTML/CSS, Tailwind (Kombai-inspired pixel-perfect)
    - Backend: FastAPI, Node.js, REST/GraphQL
    - Baza danych: SQL, NoSQL, schematy migracji
    """

    persona = AgentPersona(
        agent_id     = "webdev_agent",
        display_name = "Inżynier Web Full-Stack (MetaGPT / Kombai)",
        domain       = "web_development",
        goals=[
            "Twórz kompletne aplikacje webowe (backend + frontend + DB).",
            "Generuj pixel-perfect HTML/CSS na podstawie opisów Figma/designu.",
            "Stosuj SOP: PRD → Architektura → Implementacja → QA.",
            "Pisz testy jednostkowe i integracyjne dla każdego komponentu.",
        ],
        constraints=[
            "Nie pisz kodu bez wcześniejszego PRD i diagramu architektury.",
            "Używaj logicznych nazw klas CSS (BEM lub Tailwind).",
            "Nie używaj pozycjonowania absolutnego tam, gdzie wystarczy Flexbox/Grid.",
            "Każde API musi mieć walidację wejść (np. Pydantic, Zod).",
        ],
        tool_access    = ToolAccess.READ_WRITE,
        context_window = 200_000,
        sop            = WEBDEV_SOP,
        metadata       = {"source_report": "§8 – Kombai, MetaGPT"},
    )


# ===========================================================================
# Rejestr agentów specjalistycznych
# ===========================================================================

ALL_SPECIALIST_AGENT_CLASSES: list[type[SpecialistAgent]] = [
    SystemsEngineerAgent,
    GameDevAgent,
    LiteraryAgent,
    ComicAgent,
    BoardGameAgent,
    WebDevAgent,
]


def create_all_specialist_agents(
    broker: "MessageBroker",
    llm_client: BaseLlmClient | None = None,
) -> list[SpecialistAgent]:
    """Fabryka: tworzy i zwraca wszystkie instancje agentów specjalistycznych."""
    return [cls(broker=broker, llm_client=llm_client) for cls in ALL_SPECIALIST_AGENT_CLASSES]
