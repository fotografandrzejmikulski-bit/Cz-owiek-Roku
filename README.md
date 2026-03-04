# Człowiek Roku – Ekosystem Cross-Platform & Multi-Agent

Gra AAA na Android i Windows z zaawansowanym zapleczem **Systemu Wieloagentowego (MAS)**.
Backend oparty na autonomicznych agentach AI napędza narrację, zawartość i analizę gracza w czasie rzeczywistym.

---

## Architektura systemu

```
┌──────────────────────────────────────────────────────────────────────┐
│  KLIENCI (Frontend)                                                   │
│  ┌─────────────────────┐   ┌──────────────────────────────────────┐  │
│  │  Android (Kotlin)   │   │  Windows Desktop (C# / .NET 8)       │  │
│  │  Jetpack Compose    │   │  WinUI 3 / WPF                       │  │
│  │  MasClient.kt       │   │  MasClient.cs                        │  │
│  └──────────┬──────────┘   └──────────────┬─────────────────────┘  │
│             │ REST POST /api/v1/tasks      │ REST + WebSocket        │
│             │ WebSocket /ws               │                          │
└─────────────┼─────────────────────────────┼──────────────────────────┘
              │                             │
┌─────────────▼─────────────────────────────▼──────────────────────────┐
│  API GATEWAY (FastAPI + Uvicorn)                                       │
│  ┌─────────────────┐  ┌────────────────────┐  ┌────────────────────┐  │
│  │  REST /tasks    │  │  REST /agents      │  │  WebSocket /ws     │  │
│  │  (async push)   │  │  (status monitor)  │  │  (real-time push)  │  │
│  └────────┬────────┘  └────────────────────┘  └────────────────────┘  │
│           │                                                             │
│  ┌────────▼──────────────────────────────────────────────────────────┐ │
│  │  MESSAGE BROKER (Mediator Pattern)                                 │ │
│  │  MessageBroker – asyncio in-process │ RabbitMQ (produkcja)        │ │
│  └───────────┬──────────────────────────────────────────────────────┘ │
└──────────────┼──────────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────────┐
│  ROJ AGENTÓW AI (MAS Backend)                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  OrchestratorAgent (Mediator + Planner)                          │   │
│  │  Rejestruje agenty, buduje pipeline, deleguje podzadania         │   │
│  └──────┬─────────────────┬───────────────────────┬────────────────┘   │
│         │                 │                       │                     │
│  ┌──────▼──────┐  ┌───────▼──────────┐  ┌────────▼──────────────┐     │
│  │ContentAgent │  │  NarrativeAgent  │  │    AnalyticsAgent     │     │
│  │(enrichment, │  │(story, dialogue, │  │(player behavior,      │     │
│  │ loot_gen)   │  │ quest_design)    │  │ difficulty_tuning)    │     │
│  └─────────────┘  └──────────────────┘  └───────────────────────┘     │
│                                                                          │
│  [Przyszłość: ONNX / Llama.cpp / OpenAI dla agentów LLM-based]         │
└──────────────────────────────────────────────────────────────────────────┘
```

### Protokoły komunikacji

| Kanał | Zastosowanie | Technologia |
|-------|-------------|-------------|
| REST API | Zlecanie zadań, odczyt statusów | FastAPI (HTTP/1.1) |
| WebSocket | Push wyników do UI bez pollingu | FastAPI / `asyncio` |
| gRPC | Wydajna komunikacja binarna (NDK) | `proto/mas_service.proto` |
| In-process queue | Komunikacja między agentami | `asyncio.Queue` (Mediator) |
| External broker | Produkcja – skalowalny routing | RabbitMQ / Kafka |

---

## Struktura projektu

```
Cz-owiek-Roku/
├── src/
│   ├── agents/
│   │   ├── base_agent.py      # Abstrakcyjna klasa bazowa (SOLID/Strategy/Observer)
│   │   ├── orchestrator.py    # Orkiestrator – Mediator agentów
│   │   └── game_agents.py     # ContentAgent, NarrativeAgent, AnalyticsAgent
│   ├── api/
│   │   ├── main.py            # FastAPI app + WebSocket + lifespan
│   │   └── routers.py         # REST routery (/tasks, /agents)
│   ├── communication/
│   │   └── broker.py          # MessageBroker (Mediator Pattern)
│   ├── models/
│   │   └── message.py         # AgentMessage, MessageType, AgentStatus
│   └── config/
│       └── settings.py        # Konfiguracja przez zmienne środowiskowe
├── clients/
│   ├── android/
│   │   ├── MasClient.kt       # Klient Android (OkHttp WebSocket + REST)
│   │   └── GameViewModel.kt   # ViewModel (MVVM + StateFlow)
│   └── desktop/
│       └── MasClient.cs       # Klient Windows (C# HttpClient + WebSocket)
├── proto/
│   └── mas_service.proto      # gRPC definicja usługi (AgentService)
├── tests/
│   ├── test_mas_core.py       # Testy jednostkowe (20 testów)
│   └── test_api.py            # Testy integracyjne REST API (4 testy)
├── docker-compose.yml         # Backend + RabbitMQ + Nginx
├── Dockerfile
└── requirements.txt
```

---

## Szybki start

### Wymagania

- Python 3.11+
- Docker & Docker Compose (opcjonalne, dla pełnego stosu)

### Backend (lokalnie)

```bash
pip install -r requirements.txt
uvicorn src.api.main:app --reload
```

Swagger UI dostępny pod: **http://localhost:8000/docs**

### Pełny stos (Docker)

```bash
docker-compose up --build
```

Uruchomi:
- MAS Backend na porcie **8000**
- RabbitMQ Management UI na porcie **15672**
- Nginx reverse proxy na porcie **80**

### Testy

```bash
python -m pytest -v
# 24 passed
```

---

## Wzorce projektowe zastosowane

| Wzorzec | Gdzie | Cel |
|---------|-------|-----|
| **Mediator** | `MessageBroker`, `OrchestratorAgent` | Agenci nie wiedzą o sobie – komunikują się tylko przez brokera |
| **Strategy** | `BaseAgent.process_task()` | Każdy agent implementuje własną logikę przetwarzania |
| **Observer** | `broker.subscribe_broadcast()`, WebSocket | Klienci subskrybują zdarzenia bez pollingu |
| **MVVM** | `GameViewModel.kt` | Separacja UI i logiki biznesowej na Androidzie |
| **Circuit Breaker** | `OrchestratorAgent._delegate()` | Timeout 30s chroni przed zawieszeniem pipeline'u |

---

## Rozszerzenia produkcyjne

- **LLM lokalny**: zamień `mock` na `ONNX` / `Llama.cpp` w `ContentAgent`/`NarrativeAgent` ustawiając `LLM_BACKEND=onnx`
- **Skalowanie**: wymień `MessageBroker` na implementację z `aio_pika` (RabbitMQ) ustawiając `USE_EXTERNAL_BROKER=true`
- **gRPC**: wygeneruj kod z `proto/mas_service.proto` komendą `python -m grpc_tools.protoc`
- **Android**: dodaj `MasClient.kt` do projektu Gradle z zależnością `com.squareup.okhttp3:okhttp`
- **Windows**: dodaj `MasClient.cs` do projektu .NET 8 WinUI 3 / WPF
