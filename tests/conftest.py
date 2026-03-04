"""
Wspólna konfiguracja testów – session-scoped TestClient.

Jeden TestClient dla całej sesji testowej eliminuje problem wielokrotnego
uruchamiania/zatrzymywania cyklu życia FastAPI (lifespan) ze wspólnymi
globalnymi obiektami (broker, orchestrator).
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture(scope="session")
def app_client() -> TestClient:  # type: ignore[override]
    """
    Klient HTTP dla całej sesji testowej (jeden lifespan dla wszystkich testów).
    Użyj tego zamiast lokalnych 'api_client' w nowych testach.
    """
    from src.api.main import app
    with TestClient(app) as client:
        yield client
