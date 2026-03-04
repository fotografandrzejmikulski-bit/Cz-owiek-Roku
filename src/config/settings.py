"""
Konfiguracja systemu MAS.
Wartości domyślne możliwe do nadpisania przez zmienne środowiskowe.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    # Serwer API
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    # gRPC
    grpc_host: str = os.getenv("GRPC_HOST", "0.0.0.0")
    grpc_port: int = int(os.getenv("GRPC_PORT", "50051"))

    # Broker zewnętrzny (opcjonalne)
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
    use_external_broker: bool = os.getenv("USE_EXTERNAL_BROKER", "false").lower() == "true"

    # LLM
    llm_backend: str = os.getenv("LLM_BACKEND", "mock")  # mock | openai | gemini
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    onnx_model_path: str = os.getenv("ONNX_MODEL_PATH", "models/llm.onnx")

    # Logi
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Timeout delegowania zadań (sekundy)
    agent_task_timeout: int = int(os.getenv("AGENT_TASK_TIMEOUT", "30"))

    # ── Deep Research ──────────────────────────────────────────────────────
    # Klucz Tavily (narzędzie wyszukiwania dla agentów)
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    # Max równoległych wątków badawczych (Fan-out)
    research_max_parallel: int = int(os.getenv("RESEARCH_MAX_PARALLEL", "5"))
    # Próg jakości zatrzymujący pętle refleksji (0-100)
    research_reflection_threshold: int = int(
        os.getenv("RESEARCH_REFLECTION_THRESHOLD", "75")
    )
    # Maksymalna liczba iteracji pętli Critic→Planner
    research_max_iterations: int = int(os.getenv("RESEARCH_MAX_ITERATIONS", "3"))
    # Model LLM dla szybkich pracowników (Worker); domyślnie = llm_backend
    llm_worker_backend: str = os.getenv("LLM_WORKER_BACKEND", "")  # fallback to llm_backend

    # ── GGUF (lokalny model llama.cpp) ──────────────────────────────────────
    # Ścieżki do dwóch plików .gguf (obsługa równoległa)
    gguf_model_path_1: str = os.getenv("GGUF_MODEL_PATH_1", "")
    gguf_model_path_2: str = os.getenv("GGUF_MODEL_PATH_2", "")
    # Parametry generowania
    gguf_n_ctx: int = int(os.getenv("GGUF_N_CTX", "2048"))
    gguf_max_tokens: int = int(os.getenv("GGUF_MAX_TOKENS", "512"))
    gguf_n_threads: int = int(os.getenv("GGUF_N_THREADS", "4"))

    # ── Google OAuth2 ───────────────────────────────────────────────────────
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback"
    )
    # Klucz do podpisywania JWT sesji (minimum 32 znaki)
    jwt_secret: str = os.getenv("JWT_SECRET", "changeme-replace-in-production-32chars")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

    # ── MCP (Model Context Protocol) ───────────────────────────────────────
    mcp_server_name: str = os.getenv("MCP_SERVER_NAME", "czlowiek-roku-mcp")
    mcp_server_version: str = os.getenv("MCP_SERVER_VERSION", "1.0.0")


settings = Settings()
