"""
Abstrakcja nad modelami językowymi (LLM).

Obsługiwane backendy (wybór przez zmienną środowiskową LLM_BACKEND):
  - ``mock``   : deterministyczne odpowiedzi – środowisko deweloperskie / testy
  - ``openai`` : GPT-4o-mini / GPT-4o przez OpenAI API (wymaga OPENAI_API_KEY)
  - ``gemini`` : Google Gemini przez google-generativeai SDK (wymaga GEMINI_API_KEY)

Wzorzec: Factory + Strategy – zmiana backendu bez modyfikacji kodu agentów.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interfejs bazowy
# ---------------------------------------------------------------------------

class BaseLlmClient(ABC):
    """Wspólny interfejs dla wszystkich klientów LLM."""

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """
        Wygeneruj odpowiedź na podany prompt.

        Args:
            prompt: Tekst wejściowy dla modelu.

        Returns:
            Wygenerowana odpowiedź jako string.
        """


# ---------------------------------------------------------------------------
# Backend: Mock (domyślny, bez zależności zewnętrznych)
# ---------------------------------------------------------------------------

class MockLlmClient(BaseLlmClient):
    """Klient zaślepkowy – używany w testach i środowisku deweloperskim."""

    async def generate(self, prompt: str) -> str:
        # Krótkie opóźnienie symulujące wywołanie API
        await asyncio.sleep(0)
        snippet = prompt[:80].rstrip()
        return (
            f"[MOCK] W swiecie 'Czlowieka Roku' agenci przetworzyli: '{snippet}...' "
            "Bohater staje przed wyborem, ktory odmieni jego przeznaczenie."
        )


# ---------------------------------------------------------------------------
# Backend: OpenAI GPT
# ---------------------------------------------------------------------------

class OpenAiLlmClient(BaseLlmClient):
    """Klient OpenAI GPT (gpt-4o-mini domyślnie)."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Pakiet 'openai' nie jest zainstalowany. "
                "Uruchom: pip install openai"
            ) from exc
        import openai as _openai
        self._client = _openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        logger.info("[LLM] Używam OpenAI backend: %s", model)

    async def generate(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Jesteś narratorem mrocznej gry RPG 'Człowiek Roku'. "
                        "Odpowiadaj po polsku, krótko i dramatycznie (max 4 zdania)."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.8,
        )
        return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Backend: Google Gemini
# ---------------------------------------------------------------------------

class GeminiLlmClient(BaseLlmClient):
    """Klient Google Gemini (gemini-1.5-flash domyślnie)."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        try:
            import google.generativeai as genai  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Pakiet 'google-generativeai' nie jest zainstalowany. "
                "Uruchom: pip install google-generativeai"
            ) from exc
        import google.generativeai as _genai
        _genai.configure(api_key=api_key)
        system_instruction = (
            "Jesteś narratorem mrocznej gry RPG 'Człowiek Roku'. "
            "Odpowiadaj po polsku, krótko i dramatycznie (max 4 zdania)."
        )
        self._model = _genai.GenerativeModel(
            model_name=model,
            system_instruction=system_instruction,
        )
        logger.info("[LLM] Używam Gemini backend: %s", model)

    async def generate(self, prompt: str) -> str:
        # google-generativeai nie jest natywnie async – użyj to_thread
        response = await asyncio.to_thread(
            self._model.generate_content, prompt
        )
        return response.text or ""


# ---------------------------------------------------------------------------
# Backend: GGUF – llama.cpp via llama-cpp-python (obsługa 2 plików)
# ---------------------------------------------------------------------------

class GgufLlmClient(BaseLlmClient):
    """
    Klient lokalnych modeli w formacie GGUF (llama-cpp-python).

    Obsługuje jednocześnie dwa pliki GGUF:
      - ``path1`` : model podstawowy (domyślny)
      - ``path2`` : model alternatywny (opcjonalny, wymagany dla routing)

    Strategia wyboru modelu:
      - Jeśli prompt zawiera słowo kluczowe ``[MODEL2]`` – użyj modelu 2.
      - W pozostałych przypadkach – użyj modelu 1.
    """

    MODEL2_KEYWORD = "[MODEL2]"

    def __init__(
        self,
        path1: str,
        path2: str = "",
        n_ctx: int = 2048,
        max_tokens: int = 512,
        n_threads: int = 4,
    ) -> None:
        try:
            from llama_cpp import Llama  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Pakiet 'llama-cpp-python' nie jest zainstalowany. "
                "Uruchom: pip install llama-cpp-python"
            ) from exc

        from llama_cpp import Llama

        if not path1:
            raise ValueError("GGUF_MODEL_PATH_1 jest wymagany dla GgufLlmClient.")

        self._model1 = Llama(
            model_path=path1,
            n_ctx=n_ctx,
            n_threads=n_threads,
            verbose=False,
        )
        logger.info("[LLM] Załadowano GGUF model 1: %s", path1)

        self._model2: "Llama | None" = None
        if path2:
            self._model2 = Llama(
                model_path=path2,
                n_ctx=n_ctx,
                n_threads=n_threads,
                verbose=False,
            )
            logger.info("[LLM] Załadowano GGUF model 2: %s", path2)

        self._max_tokens = max_tokens

    def _select_model(self, prompt: str) -> Any:
        """Zwraca właściwy model na podstawie słowa kluczowego w prompcie."""
        if self.MODEL2_KEYWORD in prompt and self._model2 is not None:
            return self._model2
        return self._model1

    async def generate(self, prompt: str) -> str:
        """Generuje odpowiedź z wybranego modelu GGUF (wywołanie synchroniczne w wątku)."""
        model = self._select_model(prompt)
        clean_prompt = prompt.replace(self.MODEL2_KEYWORD, "").strip()

        def _call() -> str:
            output = model(clean_prompt, max_tokens=self._max_tokens)
            return output["choices"][0]["text"].strip()  # type: ignore[index]

        return await asyncio.to_thread(_call)



def create_llm_client(settings: "Settings | None" = None) -> BaseLlmClient:
    """
    Utwórz właściwy klient LLM na podstawie konfiguracji.

    Args:
        settings: Obiekt Settings. Jeśli None, importuje globalny singleton.

    Returns:
        Instancja klienta LLM odpowiednia do wybranego backendu.
    """
    if settings is None:
        from src.config.settings import settings as _settings
        settings = _settings

    backend = settings.llm_backend.lower()

    if backend == "openai":
        if not settings.openai_api_key:
            logger.warning(
                "[LLM] OPENAI_API_KEY nie ustawiony – przełączam na mock."
            )
            return MockLlmClient()
        return OpenAiLlmClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )

    if backend == "gemini":
        if not settings.gemini_api_key:
            logger.warning(
                "[LLM] GEMINI_API_KEY nie ustawiony – przełączam na mock."
            )
            return MockLlmClient()
        return GeminiLlmClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    if backend == "gguf":
        if not settings.gguf_model_path_1:
            logger.warning(
                "[LLM] GGUF_MODEL_PATH_1 nie ustawiony – przełączam na mock."
            )
            return MockLlmClient()
        return GgufLlmClient(
            path1=settings.gguf_model_path_1,
            path2=settings.gguf_model_path_2,
            n_ctx=settings.gguf_n_ctx,
            max_tokens=settings.gguf_max_tokens,
            n_threads=settings.gguf_n_threads,
        )

    return MockLlmClient()
