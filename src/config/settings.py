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


settings = Settings()
