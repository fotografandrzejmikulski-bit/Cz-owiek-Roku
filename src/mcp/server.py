"""
Model Context Protocol (MCP) – serwer narzędzi dla agentów i klientów zewnętrznych.

MCP (https://modelcontextprotocol.io) jest otwartym standardem Anthropic
umożliwiającym modelom AI dostęp do zewnętrznych narzędzi i kontekstu.

Ten moduł implementuje **serwer MCP** eksponujący:
  - narzędzia (tools)  : callable dostępne dla klientów MCP
  - zasoby (resources) : dane do odczytu (lista agentów, historia)
  - prompt templates   : szablony promptów

Obsługiwana specyfikacja: MCP 2024-11-05

Protokół JSON-RPC 2.0 over SSE / HTTP (transport: Streamable HTTP).
Router FastAPI montowany pod /api/v1/mcp.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typy protokołu MCP (uproszczone)
# ---------------------------------------------------------------------------

class McpError(Exception):
    """Błąd protokołu MCP."""
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code    = code
        self.message = message
        self.data    = data

    def to_dict(self) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


# Standard JSON-RPC error codes
PARSE_ERROR     = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS  = -32602
INTERNAL_ERROR  = -32603


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class McpTool:
    """Definicja narzędzia MCP."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
    ) -> None:
        self.name         = name
        self.description  = description
        self.input_schema = input_schema

    def to_dict(self) -> dict[str, Any]:
        return {
            "name":        self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class McpResource:
    """Definicja zasobu MCP."""

    def __init__(self, uri: str, name: str, description: str, mime_type: str = "application/json") -> None:
        self.uri         = uri
        self.name        = name
        self.description = description
        self.mime_type   = mime_type

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri":         self.uri,
            "name":        self.name,
            "description": self.description,
            "mimeType":    self.mime_type,
        }


class McpPromptTemplate:
    """Szablon promptu MCP."""

    def __init__(self, name: str, description: str, arguments: list[dict] | None = None) -> None:
        self.name        = name
        self.description = description
        self.arguments   = arguments or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "name":        self.name,
            "description": self.description,
            "arguments":   self.arguments,
        }


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

class McpServer:
    """
    Serwer MCP dla Człowiek Roku.

    Ekspozycja:
      Tools:
        - list_agents       : lista agentów z rejestru 51 110
        - search_agents     : wyszukiwanie agentów
        - get_agent         : szczegóły agenta
        - list_historical   : lista historycznych agentów AI
        - agent_session     : uruchomienie sesji z agentem
        - build_agent       : zbudowanie nowego agenta (no-code)

      Resources:
        - czlowiek-roku://agents        : pełna lista agentów
        - czlowiek-roku://historical    : historyczne modele AI

      Prompt Templates:
        - agent_intro       : przedstaw agenta użytkownikowi
        - task_dispatch     : przekaż zadanie do agenta
    """

    def __init__(
        self,
        name: str = "czlowiek-roku-mcp",
        version: str = "1.0.0",
    ) -> None:
        self.name    = name
        self.version = version
        self._tools:     list[McpTool]           = []
        self._resources: list[McpResource]       = []
        self._prompts:   list[McpPromptTemplate] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        # ── Narzędzia ─────────────────────────────────────────────────────
        self._tools = [
            McpTool(
                name="list_agents",
                description="Zwraca stronicowaną listę agentów z rejestru 51 110.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "offset": {"type": "integer", "default": 0},
                        "limit":  {"type": "integer", "default": 20, "maximum": 100},
                    },
                },
            ),
            McpTool(
                name="search_agents",
                description="Wyszukuje agentów po frazie w nazwie, domenie lub roli.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 20},
                    },
                    "required": ["query"],
                },
            ),
            McpTool(
                name="get_agent",
                description="Zwraca szczegóły jednego agenta po jego ID.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                    },
                    "required": ["agent_id"],
                },
            ),
            McpTool(
                name="list_historical",
                description="Zwraca listę historycznych modeli i agentów AI (151+ wpisów).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "type_filter": {"type": "string", "description": "Filtr po typie: LLM, Vision, Audio, Agent, itp."},
                        "org_filter":  {"type": "string", "description": "Filtr po organizacji."},
                        "open_source": {"type": "boolean"},
                    },
                },
            ),
            McpTool(
                name="build_agent_no_code",
                description="Tworzy nowego agenta za pomocą formularza No-Code.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "display_name":   {"type": "string"},
                        "domain":         {"type": "string"},
                        "role":           {"type": "string"},
                        "specialization": {"type": "string"},
                        "category":       {"type": "string"},
                        "safety":         {"type": "string"},
                    },
                    "required": ["display_name", "domain", "role", "specialization"],
                },
            ),
            McpTool(
                name="get_server_info",
                description="Zwraca informacje o serwerze MCP i dostępnych zasobach.",
                input_schema={"type": "object", "properties": {}},
            ),
        ]

        # ── Zasoby ────────────────────────────────────────────────────────
        self._resources = [
            McpResource(
                uri="czlowiek-roku://agents",
                name="Agent Registry",
                description="Pełny rejestr 51 110 unikalnych agentów.",
            ),
            McpResource(
                uri="czlowiek-roku://historical",
                name="Historical AI Catalog",
                description="Katalog 151+ historycznych modeli i agentów AI.",
            ),
            McpResource(
                uri="czlowiek-roku://custom-agents",
                name="Custom Agents",
                description="Agenci zbudowani przez użytkowników (Agent Builder).",
            ),
        ]

        # ── Szablony promptów ─────────────────────────────────────────────
        self._prompts = [
            McpPromptTemplate(
                name="agent_intro",
                description="Generuje wprowadzenie agenta dla użytkownika.",
                arguments=[
                    {"name": "agent_id",    "description": "ID agenta", "required": True},
                    {"name": "user_name",   "description": "Imię użytkownika", "required": False},
                ],
            ),
            McpPromptTemplate(
                name="task_dispatch",
                description="Przekazuje zadanie do wybranego agenta.",
                arguments=[
                    {"name": "agent_id", "description": "ID agenta",  "required": True},
                    {"name": "task",     "description": "Opis zadania", "required": True},
                ],
            ),
        ]

    # ── JSON-RPC dispatcher ───────────────────────────────────────────────

    async def handle_request(self, body: dict[str, Any]) -> dict[str, Any]:
        """Obsługuje pojedyncze żądanie JSON-RPC 2.0."""
        req_id  = body.get("id")
        method  = body.get("method", "")
        params  = body.get("params", {})

        try:
            result = await self._dispatch(method, params)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except McpError as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": exc.to_dict(),
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("[MCP] Nieobsłużony błąd: %s", exc)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": INTERNAL_ERROR, "message": str(exc)},
            }

    async def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        handlers = {
            "initialize":               self._handle_initialize,
            "tools/list":               self._handle_tools_list,
            "tools/call":               self._handle_tools_call,
            "resources/list":           self._handle_resources_list,
            "resources/read":           self._handle_resources_read,
            "prompts/list":             self._handle_prompts_list,
            "prompts/get":              self._handle_prompts_get,
            "ping":                     self._handle_ping,
        }
        handler = handlers.get(method)
        if handler is None:
            raise McpError(METHOD_NOT_FOUND, f"Nieznana metoda: {method!r}")
        return await handler(params)

    # ── Handlers ──────────────────────────────────────────────────────────

    async def _handle_initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools":     {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
                "prompts":   {"listChanged": False},
            },
            "serverInfo": {
                "name":    self.name,
                "version": self.version,
            },
        }

    async def _handle_ping(self, params: dict) -> dict:
        return {}

    async def _handle_tools_list(self, params: dict) -> dict:
        return {"tools": [t.to_dict() for t in self._tools]}

    async def _handle_tools_call(self, params: dict) -> dict:
        name       = params.get("name", "")
        arguments  = params.get("arguments", {})
        tool_map   = {t.name: t for t in self._tools}

        if name not in tool_map:
            raise McpError(INVALID_PARAMS, f"Narzędzie nieznane: {name!r}")

        result = await self._execute_tool(name, arguments)
        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
        }

    async def _execute_tool(self, name: str, args: dict) -> Any:
        from src.agents.agent_registry import get_default_registry
        from src.agents.agent_builder import NoCodeBuilder, CustomAgentStore

        if name == "list_agents":
            reg     = get_default_registry()
            offset  = int(args.get("offset", 0))
            limit   = min(int(args.get("limit", 20)), 100)
            entries = reg.page(offset=offset, limit=limit)
            return {"total": reg.count(), "agents": [e.to_dict() for e in entries]}

        if name == "search_agents":
            reg     = get_default_registry()
            query   = args.get("query", "")
            limit   = min(int(args.get("limit", 20)), 100)
            entries = reg.search(query, limit=limit)
            return {"count": len(entries), "agents": [e.to_dict() for e in entries]}

        if name == "get_agent":
            reg     = get_default_registry()
            agent_id = args.get("agent_id", "")
            entry    = reg.get(agent_id)
            if entry is None:
                raise McpError(INVALID_PARAMS, f"Agent nieznany: {agent_id!r}")
            return entry.to_dict()

        if name == "list_historical":
            from src.api.routers import _load_historical_agents
            agents = _load_historical_agents()
            type_f = args.get("type_filter", "").lower()
            org_f  = args.get("org_filter", "").lower()
            os_f   = args.get("open_source")
            if type_f:
                agents = [a for a in agents if type_f in a.get("type", "").lower()]
            if org_f:
                agents = [a for a in agents if org_f in a.get("org", "").lower()]
            if os_f is not None:
                agents = [a for a in agents if a.get("open_source") == os_f]
            return {"count": len(agents), "agents": agents}

        if name == "build_agent_no_code":
            builder = NoCodeBuilder()
            store   = CustomAgentStore()
            spec    = builder.build(
                display_name  = args.get("display_name", "Nowy Agent"),
                domain        = args.get("domain", "Technologia"),
                role          = args.get("role", "Asystent"),
                specialization= args.get("specialization", "Danych"),
                category      = args.get("category", "specialist"),
                safety        = args.get("safety", "safe"),
                created_by    = "mcp-client",
            )
            store.add(spec)
            return spec.to_dict()

        if name == "get_server_info":
            return {
                "name":          self.name,
                "version":       self.version,
                "tools_count":   len(self._tools),
                "resources":     [r.to_dict() for r in self._resources],
                "registry_size": get_default_registry().count(),
                "timestamp":     datetime.now(timezone.utc).isoformat(),
            }

        raise McpError(INTERNAL_ERROR, f"Niezaimplementowane narzędzie: {name!r}")

    async def _handle_resources_list(self, params: dict) -> dict:
        return {"resources": [r.to_dict() for r in self._resources]}

    async def _handle_resources_read(self, params: dict) -> dict:
        uri = params.get("uri", "")
        content = await self._read_resource(uri)
        return {
            "contents": [{
                "uri":      uri,
                "mimeType": "application/json",
                "text":     json.dumps(content, ensure_ascii=False),
            }]
        }

    async def _read_resource(self, uri: str) -> Any:
        from src.agents.agent_registry import get_default_registry

        if uri == "czlowiek-roku://agents":
            reg = get_default_registry()
            return {"total": reg.count(), "agents": [e.to_dict() for e in reg.page(0, 100)]}

        if uri == "czlowiek-roku://historical":
            from src.api.routers import _load_historical_agents
            agents = _load_historical_agents()
            return {"total": len(agents), "agents": agents}

        if uri == "czlowiek-roku://custom-agents":
            from src.agents.agent_builder import CustomAgentStore
            store = CustomAgentStore()
            return {"total": store.count(), "agents": [a.to_dict() for a in store.all()]}

        raise McpError(INVALID_PARAMS, f"Nieznany zasób: {uri!r}")

    async def _handle_prompts_list(self, params: dict) -> dict:
        return {"prompts": [p.to_dict() for p in self._prompts]}

    async def _handle_prompts_get(self, params: dict) -> dict:
        name   = params.get("name", "")
        p_map  = {p.name: p for p in self._prompts}
        if name not in p_map:
            raise McpError(INVALID_PARAMS, f"Szablon nieznany: {name!r}")
        args   = params.get("arguments", {})
        tmpl   = p_map[name]

        if name == "agent_intro":
            agent_id  = args.get("agent_id", "agent_0001")
            user_name = args.get("user_name", "Użytkowniku")
            from src.agents.agent_registry import get_default_registry
            entry = get_default_registry().get(agent_id)
            if entry:
                text = (
                    f"Cześć, {user_name}! Jestem {entry.display_name}. "
                    f"Moja misja: {entry.mission}"
                )
            else:
                text = f"Cześć, {user_name}! Jestem agentem {agent_id}."

        elif name == "task_dispatch":
            agent_id = args.get("agent_id", "")
            task     = args.get("task", "")
            text     = f"Agent {agent_id}, proszę wykonaj następujące zadanie:\n{task}"

        else:
            text = ""

        return {
            "description": tmpl.description,
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

from functools import lru_cache


@lru_cache(maxsize=1)
def get_mcp_server() -> McpServer:
    from src.config.settings import settings
    return McpServer(name=settings.mcp_server_name, version=settings.mcp_server_version)
