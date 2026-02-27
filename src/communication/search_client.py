"""
Klient wyszukiwania dla agentów Deep Research.

Obsługiwane backendy (przez TAVILY_API_KEY):
  - mock   : deterministyczne wyniki zaślepkowe (dev / testy)
  - tavily : Tavily Search API – zoptymalizowane pod AI (produkcja)

Wzorzec: Strategy – podmiana backendu bez zmian w kodzie agentów.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model wyniku wyszukiwania
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """Pojedynczy wynik zwrócony przez wyszukiwarkę."""
    url: str
    title: str
    content: str
    score: float = 1.0


# ---------------------------------------------------------------------------
# Interfejs bazowy
# ---------------------------------------------------------------------------

class BaseSearchClient(ABC):
    """Wspólny interfejs dla wszystkich klientów wyszukiwania."""

    @abstractmethod
    async def search(
        self, query: str, max_results: int = 5
    ) -> list[SearchResult]:
        """
        Wyszukaj informacje i zwróć listę wyników.

        Args:
            query:       Zapytanie w języku naturalnym.
            max_results: Maksymalna liczba wyników.

        Returns:
            Lista wyników posortowanych malejąco według trafności.
        """


# ---------------------------------------------------------------------------
# Backend: Mock
# ---------------------------------------------------------------------------

class MockSearchClient(BaseSearchClient):
    """Klient zaślepkowy – deterministyczny, bez wywołań sieciowych."""

    async def search(
        self, query: str, max_results: int = 5
    ) -> list[SearchResult]:
        await asyncio.sleep(0)
        slug = query[:40].replace(" ", "-").lower()
        return [
            SearchResult(
                url=f"https://example.com/{slug}/{i + 1}",
                title=f"Artykul {i + 1}: {query[:55]}",
                content=(
                    f"Obszerne omowienie tematu '{query}'. "
                    f"Kluczowe wnioski ({i + 1}/3): analiza danych potwierdza "
                    f"glowne zalozenia. Eksperckie opinie wskazuja na wysoka "
                    f"trafnosc wynikow badan empirycznych."
                ),
                score=round(0.95 - i * 0.08, 2),
            )
            for i in range(min(3, max_results))
        ]


# ---------------------------------------------------------------------------
# Backend: Tavily
# ---------------------------------------------------------------------------

class TavilySearchClient(BaseSearchClient):
    """
    Klient Tavily Search – wyszukiwarka zoptymalizowana pod agenty AI.

    Tavily filtruje szum (reklamy, clickbait) i zwraca syntetyczne
    fragmenty treści gotowe do bezpośredniego załadowania do okna
    kontekstowego LLM.
    """

    def __init__(
        self, api_key: str, search_depth: str = "advanced"
    ) -> None:
        try:
            from tavily import TavilyClient  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Pakiet 'tavily-python' nie jest zainstalowany. "
                "Uruchom: pip install tavily-python"
            ) from exc
        from tavily import TavilyClient as _TC
        self._client = _TC(api_key=api_key)
        self._depth = search_depth
        logger.info("[Search] Tavily aktywny (depth=%s).", search_depth)

    async def search(
        self, query: str, max_results: int = 5
    ) -> list[SearchResult]:
        raw = await asyncio.to_thread(
            self._client.search,
            query=query,
            search_depth=self._depth,
            max_results=max_results,
        )
        return [
            SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                content=r.get("content", ""),
                score=float(r.get("score", 1.0)),
            )
            for r in raw.get("results", [])
        ]


# ---------------------------------------------------------------------------
# Fabryka
# ---------------------------------------------------------------------------

def create_search_client(settings: "Settings | None" = None) -> BaseSearchClient:
    """
    Utwórz właściwy klient wyszukiwania na podstawie konfiguracji.

    Jeśli TAVILY_API_KEY jest ustawiony, zwraca TavilySearchClient.
    W przeciwnym razie zwraca MockSearchClient.
    """
    if settings is None:
        from src.config.settings import settings as _s
        settings = _s

    if settings.tavily_api_key:
        return TavilySearchClient(api_key=settings.tavily_api_key)

    logger.info(
        "[Search] TAVILY_API_KEY nie ustawiony – uzywam MockSearchClient."
    )
    return MockSearchClient()
