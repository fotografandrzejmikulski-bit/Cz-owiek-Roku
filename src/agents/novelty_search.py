"""
MAP-Elites: Algorytm Jakości-Różnorodności dla Proceduralnej Generacji Treści (PCG).

Implementacja oparta na §7 raportu "Ekosystem Autonomicznych Agentów AI
w Inżynierii Systemowej i Procesach Kreatywnych (2025-2026)".

Dostarcza:
    GridArchive      – archiwum elitarnych rozwiązań na siatce cech behawioralnych
    GaussianEmitter  – generator nowych rozwiązań (mutacja gaussowska)
    MapElitesScheduler – pętla ewolucyjna Map-Elites
    NoveltyEvaluator – interfejs do oceny rozwiązań przez LLM lub funkcję analityczną

Nie wymaga zewnętrznych zależności (tylko stdlib + numpy jeśli dostępny,
z fallbackiem na czysty Python).
"""
from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Sprawdź dostępność numpy (opcjonalna zależność)
# ---------------------------------------------------------------------------
try:
    import numpy as np  # type: ignore
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Typy
# ---------------------------------------------------------------------------
Solution   = list[float]   # wektor genotypu
Behavior   = tuple[float, ...]  # współrzędne behawioralne (cechy)
Objective  = float         # wartość fitness (jakość)


# ---------------------------------------------------------------------------
# GridArchive – siatka elitarnych rozwiązań
# ---------------------------------------------------------------------------

@dataclass
class EliteCell:
    """Komórka w siatce archiwum – przechowuje najlepsze rozwiązanie dla danej cechy."""
    solution:  Solution
    objective: Objective
    behavior:  Behavior
    metadata:  dict[str, Any] = field(default_factory=dict)


class GridArchive:
    """
    Dwuwymiarowa siatka elitarnych rozwiązań (MAP-Elites).

    Każda komórka (i, j) przechowuje rozwiązanie o najwyższej jakości
    wśród wszystkich rozwiązań, których cechy behawioralne mapują się
    na tę komórkę.

    Przykład zastosowania w PCG:
        Oś 0 = liczba wrogów (0.0–1.0 → 0–50 wrogów)
        Oś 1 = liczba platform (0.0–1.0 → 0–100 platform)
        Każda komórka = najlepszy poziom z daną kombinacją tych cech
    """

    def __init__(
        self,
        solution_dim: int,
        dims: list[int],
        ranges: list[tuple[float, float]],
    ) -> None:
        """
        Argumenty:
            solution_dim: Wymiar wektora rozwiązania (genotypu).
            dims:         Liczba komórek na każdej osi [oś0, oś1, ...].
            ranges:       Zakresy wartości dla każdej osi [(min,max), ...].
        """
        if len(dims) != len(ranges):
            raise ValueError("dims i ranges muszą mieć tę samą długość")
        self.solution_dim = solution_dim
        self.dims         = dims
        self.ranges       = ranges
        self._cells: dict[tuple[int, ...], EliteCell] = {}

    # ------------------------------------------------------------------

    def _behavior_to_index(self, behavior: Behavior) -> tuple[int, ...]:
        """Mapuje wartości cech behawioralnych na indeks komórki siatki."""
        idx = []
        for val, dim, (lo, hi) in zip(behavior, self.dims, self.ranges):
            # Clamp + normalizacja → indeks komórki
            clamped = max(lo, min(hi, val))
            normalized = (clamped - lo) / (hi - lo) if hi > lo else 0.0
            cell_i = min(int(normalized * dim), dim - 1)
            idx.append(cell_i)
        return tuple(idx)

    def add(
        self,
        solution: Solution,
        objective: Objective,
        behavior: Behavior,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Dodaj rozwiązanie do archiwum.

        Zwraca True jeśli rozwiązanie poprawiło lub wypełniło komórkę.
        """
        idx = self._behavior_to_index(behavior)
        existing = self._cells.get(idx)
        if existing is None or objective > existing.objective:
            self._cells[idx] = EliteCell(
                solution=list(solution),
                objective=objective,
                behavior=behavior,
                metadata=metadata or {},
            )
            return True
        return False

    def sample_elite(self) -> EliteCell | None:
        """Losuj elitarne rozwiązanie z archiwum."""
        if not self._cells:
            return None
        return random.choice(list(self._cells.values()))

    @property
    def size(self) -> int:
        """Liczba wypełnionych komórek."""
        return len(self._cells)

    @property
    def total_cells(self) -> int:
        """Łączna liczba komórek siatki."""
        total = 1
        for d in self.dims:
            total *= d
        return total

    def coverage(self) -> float:
        """Procent wypełnionych komórek (0.0–1.0)."""
        return self.size / self.total_cells if self.total_cells else 0.0

    def best_elite(self) -> EliteCell | None:
        """Zwraca elitę z najwyższą wartością fitness."""
        if not self._cells:
            return None
        return max(self._cells.values(), key=lambda e: e.objective)

    def to_dict(self) -> dict[str, Any]:
        return {
            "solution_dim": self.solution_dim,
            "dims":         self.dims,
            "ranges":       self.ranges,
            "size":         self.size,
            "total_cells":  self.total_cells,
            "coverage":     round(self.coverage(), 4),
        }


# ---------------------------------------------------------------------------
# GaussianEmitter – generator nowych kandydatów
# ---------------------------------------------------------------------------

class GaussianEmitter:
    """
    Emiter gaussowski: generuje nowe rozwiązania przez perturbację
    losowo wybranej elity z archiwum.

    Jeśli archiwum jest puste, inicjalizuje losowe rozwiązania z rozkładem
    jednostajnym na [0, 1]^n.
    """

    def __init__(
        self,
        archive: GridArchive,
        sigma: float = 0.1,
        batch_size: int = 32,
    ) -> None:
        self.archive    = archive
        self.sigma      = sigma
        self.batch_size = batch_size

    def ask(self) -> list[Solution]:
        """Generuj `batch_size` nowych kandydatów."""
        solutions = []
        for _ in range(self.batch_size):
            elite = self.archive.sample_elite()
            if elite is None:
                # Archiwum puste – losuj z rozkładu jednostajnego
                sol = [random.random() for _ in range(self.archive.solution_dim)]
            else:
                # Perturbacja gaussowska wokół elity
                sol = [
                    x + random.gauss(0.0, self.sigma)
                    for x in elite.solution
                ]
            # Clamp do [0, 1]
            sol = [max(0.0, min(1.0, x)) for x in sol]
            solutions.append(sol)
        return solutions


# ---------------------------------------------------------------------------
# MapElitesScheduler – pętla ewolucyjna
# ---------------------------------------------------------------------------

EvaluatorFn = Callable[
    [list[Solution]],
    tuple[list[Objective], list[Behavior]],
]
"""
Sygnatura funkcji ewaluatora:
    Wejście:  lista rozwiązań (genotypów)
    Wyjście:  (lista wartości fitness, lista wektorów cech behawioralnych)
"""


class MapElitesScheduler:
    """
    Pętla ewolucyjna MAP-Elites.

    Schemat każdej iteracji:
        1. ask()  – emiter generuje kandydatów
        2. (zewnętrzna) ewaluacja w symulatorze / grze / LLM
        3. tell() – wyniki wracają do archiwum
    """

    def __init__(
        self,
        archive: GridArchive,
        emitters: list[GaussianEmitter],
    ) -> None:
        self.archive  = archive
        self.emitters = emitters
        self._iteration = 0
        self._last_solutions: list[Solution] = []

    def ask(self) -> list[Solution]:
        """Generuj nową porcję kandydatów ze wszystkich emiterów."""
        solutions: list[Solution] = []
        for emitter in self.emitters:
            solutions.extend(emitter.ask())
        self._last_solutions = solutions
        return solutions

    def tell(
        self,
        objectives: list[Objective],
        behaviors: list[Behavior],
        metadata: list[dict[str, Any]] | None = None,
    ) -> int:
        """
        Zaktualizuj archiwum wynikami ewaluacji.

        Zwraca liczbę zaktualizowanych komórek w tej iteracji.
        """
        if len(objectives) != len(self._last_solutions):
            raise ValueError(
                f"Oczekiwano {len(self._last_solutions)} wyników, "
                f"otrzymano {len(objectives)}."
            )
        updated = 0
        meta_list = metadata or [{}] * len(objectives)
        for sol, obj, beh, meta in zip(
            self._last_solutions, objectives, behaviors, meta_list
        ):
            if self.archive.add(sol, obj, beh, meta):
                updated += 1
        self._iteration += 1
        return updated

    def run(
        self,
        evaluator: EvaluatorFn,
        iterations: int = 100,
    ) -> GridArchive:
        """
        Uruchom pełną pętlę ewolucyjną.

        Argumenty:
            evaluator:  Funkcja oceniająca rozwiązania (batchowo).
            iterations: Liczba generacji.

        Zwraca:
            Wypełnione archiwum GridArchive.
        """
        for _ in range(iterations):
            solutions = self.ask()
            objectives, behaviors = evaluator(solutions)
            self.tell(objectives, behaviors)
        return self.archive

    @property
    def iteration(self) -> int:
        return self._iteration

    def stats(self) -> dict[str, Any]:
        return {
            "iteration":      self._iteration,
            "archive_size":   self.archive.size,
            "total_cells":    self.archive.total_cells,
            "coverage":       round(self.archive.coverage(), 4),
            "best_objective": (
                self.archive.best_elite().objective
                if self.archive.best_elite() else None
            ),
        }


# ---------------------------------------------------------------------------
# NoveltyEvaluator – prosta funkcja oceny (bez zewnętrznych zależności)
# ---------------------------------------------------------------------------

class NoveltyEvaluator:
    """
    Przykładowy ewaluator dla generatora poziomów gry (demonstracja MAP-Elites).

    Interpretacja wektora rozwiązania (10 genów [0,1]):
        gen[0]:  gęstość wrogów (0 = brak, 1 = bardzo dużo)
        gen[1]:  liczba platform (0 = mało, 1 = bardzo dużo)
        gen[2]:  trudność pułapek
        gen[3]:  otwartość przestrzeni (0 = korytarze, 1 = otwarte)
        gen[4]:  skarby / nagrody
        gen[5..9]: dodatkowe cechy stylistyczne

    Metryki behawioralne:
        oś 0: gęstość wrogów  (gen[0])
        oś 1: liczba platform (gen[1])

    Fitness: "grywalność" – kara za skrajności (zbyt łatwy lub zbyt trudny poziom).
    """

    @staticmethod
    def evaluate(solutions: list[Solution]) -> tuple[list[Objective], list[Behavior]]:
        objectives: list[Objective] = []
        behaviors:  list[Behavior]  = []

        for sol in solutions:
            enemies   = sol[0] if len(sol) > 0 else 0.5
            platforms = sol[1] if len(sol) > 1 else 0.5
            traps     = sol[2] if len(sol) > 2 else 0.5
            openness  = sol[3] if len(sol) > 3 else 0.5

            # Fitness = grywalność (penalizuj skrajne wartości)
            balance_penalty = (
                abs(enemies - 0.5)   * 0.4 +
                abs(platforms - 0.5) * 0.3 +
                abs(traps - 0.5)     * 0.2 +
                abs(openness - 0.5)  * 0.1
            )
            fitness = 1.0 - balance_penalty  # im bliżej 0.5 tym lepiej

            objectives.append(round(fitness, 4))
            behaviors.append((round(enemies, 3), round(platforms, 3)))

        return objectives, behaviors
