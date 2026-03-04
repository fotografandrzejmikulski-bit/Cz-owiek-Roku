"""
Modele stanu procesu Deep Research.

ResearchState to "żywa tablica" współdzielona przez wszystkie węzły
potoku badawczego: Planner → Researcher(s) → Critic → Writer.
Wzorzec: inspirowany zarządzaniem stanem z LangGraph (State Graph).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResearchStatus(str, Enum):
    """Etapy potoku Deep Research."""
    PENDING = "pending"
    PLANNING = "planning"
    RESEARCHING = "researching"
    REFLECTING = "reflecting"
    WRITING = "writing"
    DONE = "done"
    ERROR = "error"


@dataclass
class ResearchPlan:
    """Plan badawczy wygenerowany przez agenta Planner."""
    main_query: str
    sub_questions: list[str]
    source_strategy: str = "general"
    success_criteria: list[str] = field(default_factory=list)


@dataclass
class ResearchFinding:
    """Wynik badania jednego pytania pomocniczego."""
    sub_question: str
    summary: str
    sources: list[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class ResearchState:
    """
    Centralny obiekt stanu potoku Deep Research.

    Przekazywany kolejno przez wszystkie węzły, każdy zapisuje
    swoje wyniki bezpośrednio w polach tego obiektu.
    """
    query: str
    plan: ResearchPlan | None = None
    findings: list[ResearchFinding] = field(default_factory=list)
    draft: str = ""
    quality_score: int = 0
    feedback: list[str] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 3
    reflection_threshold: int = 75
    final_report: str = ""
    status: ResearchStatus = ResearchStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "status": self.status.value,
            "iteration": self.iteration,
            "quality_score": self.quality_score,
            "sub_questions": self.plan.sub_questions if self.plan else [],
            "findings_count": len(self.findings),
            "final_report": self.final_report,
            "feedback": self.feedback,
        }
