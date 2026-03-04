"""
Testy dla nowych komponentów:
  - Historical AI Catalog (data/historical_agents.json + /historical/* API)
  - GGUF Dual-Model LLM Client (GgufLlmClient)
  - Agent Builder (ProCodeBuilder, NoCodeBuilder, HybridBuilder)
  - Google OAuth2 Auth (GoogleAuthService, JWT)
  - MCP Server (McpServer, JSON-RPC)
  - API endpoints dla wszystkich powyższych
"""
from __future__ import annotations

import json
import pytest

from src.agents.agent_builder import (
    CustomAgentSpec,
    CustomAgentStore,
    HybridBuilder,
    NoCodeBuilder,
    ProCodeBuilder,
)
from src.api.auth import GoogleAuthService
from src.communication.broker import MessageBroker
from src.communication.llm_client import GgufLlmClient, MockLlmClient
from src.mcp.server import McpServer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def broker() -> MessageBroker:
    return MessageBroker()


@pytest.fixture
def mock_llm() -> MockLlmClient:
    return MockLlmClient()


@pytest.fixture(scope="module")
def client(app_client):
    return app_client


@pytest.fixture
def auth_service() -> GoogleAuthService:
    return GoogleAuthService(
        client_id="test-client-id",
        client_secret="test-secret",
        redirect_uri="http://localhost/callback",
        jwt_secret="testsecretkey32charslongrequired!!",
        jwt_algorithm="HS256",
        jwt_expire_minutes=60,
    )


@pytest.fixture
def mcp_server() -> McpServer:
    return McpServer(name="test-mcp", version="0.1.0")


@pytest.fixture
def no_code_builder() -> NoCodeBuilder:
    return NoCodeBuilder()


@pytest.fixture
def pro_code_builder() -> ProCodeBuilder:
    return ProCodeBuilder()


@pytest.fixture
def hybrid_builder() -> HybridBuilder:
    return HybridBuilder()


@pytest.fixture
def custom_store(tmp_path) -> CustomAgentStore:
    """CustomAgentStore używający tymczasowego pliku."""
    return CustomAgentStore(path=tmp_path / "custom_agents.json")


# ===========================================================================
# 1. Historical AI Catalog
# ===========================================================================

class TestHistoricalAgentsCatalog:
    def test_file_exists(self) -> None:
        from pathlib import Path
        path = Path("data/historical_agents.json")
        assert path.exists(), "data/historical_agents.json nie istnieje"

    def test_has_at_least_100_agents(self) -> None:
        from pathlib import Path
        agents = json.loads(Path("data/historical_agents.json").read_text())
        assert len(agents) >= 100

    def test_all_ids_unique(self) -> None:
        from pathlib import Path
        agents = json.loads(Path("data/historical_agents.json").read_text())
        ids = [a["id"] for a in agents]
        assert len(set(ids)) == len(ids)

    def test_required_fields_present(self) -> None:
        from pathlib import Path
        agents = json.loads(Path("data/historical_agents.json").read_text())
        for a in agents[:20]:
            for field in ("id", "name", "org", "year", "type", "description"):
                assert field in a, f"Brakuje pola {field!r} w {a.get('id')}"

    def test_known_models_present(self) -> None:
        from pathlib import Path
        agents = json.loads(Path("data/historical_agents.json").read_text())
        ids = {a["id"] for a in agents}
        for known in ("gpt-4", "claude-3-opus", "llama-3", "alphafold-2", "bert", "eliza"):
            assert known in ids, f"Brakuje agenta: {known!r}"

    def test_type_diversity(self) -> None:
        from pathlib import Path
        agents = json.loads(Path("data/historical_agents.json").read_text())
        types = {a["type"] for a in agents}
        assert len(types) >= 5

    def test_open_source_flag_is_bool(self) -> None:
        from pathlib import Path
        agents = json.loads(Path("data/historical_agents.json").read_text())
        for a in agents:
            assert isinstance(a.get("open_source"), bool), f"open_source nie jest bool w {a['id']}"


class TestHistoricalAPI:
    def test_list_all(self, client) -> None:
        r = client.get("/api/v1/historical/agents")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 100
        assert len(data["agents"]) > 0

    def test_filter_by_type(self, client) -> None:
        r = client.get("/api/v1/historical/agents?type_filter=LLM")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0
        for a in data["agents"]:
            assert "LLM" in a["type"]

    def test_filter_open_source(self, client) -> None:
        r = client.get("/api/v1/historical/agents?open_source=true")
        assert r.status_code == 200
        for a in r.json()["agents"]:
            assert a["open_source"] is True

    def test_get_by_id_ok(self, client) -> None:
        r = client.get("/api/v1/historical/agents/gpt-4")
        assert r.status_code == 200
        assert r.json()["id"] == "gpt-4"

    def test_get_by_id_not_found(self, client) -> None:
        r = client.get("/api/v1/historical/agents/nonexistent-xyz-000")
        assert r.status_code == 404

    def test_stats_endpoint(self, client) -> None:
        r = client.get("/api/v1/historical/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "by_type" in data
        assert "open_source" in data
        assert data["total"] >= 100


# ===========================================================================
# 2. GGUF Dual-Model LLM Client
# ===========================================================================

class TestGgufLlmClient:
    def test_requires_path1(self) -> None:
        """Powinien rzucić ImportError (llama-cpp-python) lub ValueError."""
        try:
            GgufLlmClient(path1="")
        except (ImportError, ValueError) as exc:
            assert "GGUF_MODEL_PATH_1" in str(exc) or "llama" in str(exc).lower()

    def test_model2_keyword_constant(self) -> None:
        assert GgufLlmClient.MODEL2_KEYWORD == "[MODEL2]"

    def test_factory_returns_mock_without_path(self) -> None:
        """create_llm_client(backend=gguf) bez ścieżki → MockLlmClient."""
        from src.communication.llm_client import create_llm_client
        from src.config.settings import Settings
        s = Settings()
        s.llm_backend = "gguf"
        s.gguf_model_path_1 = ""  # brak ścieżki
        client = create_llm_client(settings=s)
        assert isinstance(client, MockLlmClient)

    def test_factory_mock_backend(self) -> None:
        from src.communication.llm_client import create_llm_client
        from src.config.settings import Settings
        s = Settings()
        s.llm_backend = "mock"
        assert isinstance(create_llm_client(settings=s), MockLlmClient)

    @pytest.mark.asyncio
    async def test_mock_generate_returns_string(self, mock_llm: MockLlmClient) -> None:
        result = await mock_llm.generate("Testowy prompt")
        assert isinstance(result, str)
        assert len(result) > 0


# ===========================================================================
# 3. Agent Builder
# ===========================================================================

class TestNoCodeBuilder:
    def test_build_returns_spec(self, no_code_builder: NoCodeBuilder) -> None:
        spec = no_code_builder.build(
            display_name="Mój Agent",
            domain="Medycyna",
            role="Analityk",
            specialization="Ryzyka",
        )
        assert isinstance(spec, CustomAgentSpec)
        assert spec.display_name == "Mój Agent"
        assert spec.domain == "Medycyna"
        assert spec.role == "Analityk"
        assert spec.specialization == "Ryzyka"
        assert spec.builder_mode == "no_code"
        assert spec.agent_id.startswith("custom_")
        assert spec.created_at

    def test_system_prompt_auto_generated(self, no_code_builder: NoCodeBuilder) -> None:
        spec = no_code_builder.build(
            display_name="Agent",
            domain="Prawo",
            role="Doradca",
            specialization="Zgodności",
        )
        assert "Doradca" in spec.system_prompt
        assert "Prawo" in spec.system_prompt

    def test_invalid_domain_raises(self, no_code_builder: NoCodeBuilder) -> None:
        with pytest.raises(ValueError, match="Nieznana domena"):
            no_code_builder.build("X", "NIEZNANA_DOMENA", "Analityk", "Ryzyka")

    def test_invalid_role_raises(self, no_code_builder: NoCodeBuilder) -> None:
        with pytest.raises(ValueError, match="Nieznana rola"):
            no_code_builder.build("X", "Medycyna", "NIEZNANA_ROLA", "Ryzyka")

    def test_invalid_safety_raises(self, no_code_builder: NoCodeBuilder) -> None:
        with pytest.raises(ValueError, match="Nieznany poziom"):
            no_code_builder.build("X", "Medycyna", "Analityk", "Ryzyka", safety="INVALID")

    def test_get_form_options(self) -> None:
        opts = NoCodeBuilder.get_form_options()
        assert "domains" in opts
        assert "roles" in opts
        assert "categories" in opts
        assert "safety" in opts
        assert len(opts["domains"]) > 0

    def test_extra_instructions_in_prompt(self, no_code_builder: NoCodeBuilder) -> None:
        spec = no_code_builder.build(
            "X", "Prawo", "Ekspert", "Danych",
            extra_instructions="Mów po angielsku."
        )
        assert "Mów po angielsku" in spec.system_prompt


class TestProCodeBuilder:
    def _valid_payload(self) -> dict:
        return {
            "display_name":   "Pro Agent",
            "domain":         "Finanse",
            "role":           "Strateg",
            "specialization": "Ryzyka",
            "mission":        "Strategiczne zarządzanie ryzykiem.",
            "system_prompt":  "Jesteś ekspertem finansowym. Analizuj ryzyko precyzyjnie.",
            "category":       "specialist",
            "safety":         "safe",
        }

    def test_build_returns_spec(self, pro_code_builder: ProCodeBuilder) -> None:
        spec = pro_code_builder.build(self._valid_payload())
        assert spec.builder_mode == "pro_code"
        assert spec.domain == "Finanse"

    def test_missing_field_raises(self, pro_code_builder: ProCodeBuilder) -> None:
        payload = self._valid_payload()
        del payload["system_prompt"]
        with pytest.raises(ValueError, match="Brakujące pola"):
            pro_code_builder.build(payload)

    def test_short_prompt_raises(self, pro_code_builder: ProCodeBuilder) -> None:
        payload = self._valid_payload()
        payload["system_prompt"] = "Za krótki"
        with pytest.raises(ValueError, match="za krótki"):
            pro_code_builder.build(payload)

    def test_custom_code_preserved(self, pro_code_builder: ProCodeBuilder) -> None:
        payload = self._valid_payload()
        payload["custom_code"] = "def run(): pass"
        spec = pro_code_builder.build(payload)
        assert spec.custom_code == "def run(): pass"

    def test_created_by_set(self, pro_code_builder: ProCodeBuilder) -> None:
        spec = pro_code_builder.build(self._valid_payload(), created_by="test@example.com")
        assert spec.created_by == "test@example.com"


class TestHybridBuilder:
    def test_build_hybrid_mode(self, hybrid_builder: HybridBuilder) -> None:
        spec = hybrid_builder.build(
            display_name="Hybrid Agent",
            domain="Nauka",
            role="Badacz",
            specialization="Syntezy",
        )
        assert spec.builder_mode == "hybrid"

    def test_system_prompt_override(self, hybrid_builder: HybridBuilder) -> None:
        override = "Niestandardowy prompt systemowy dla testu."
        spec = hybrid_builder.build(
            "X", "Nauka", "Badacz", "Syntezy",
            system_prompt_override=override,
        )
        assert spec.system_prompt == override

    def test_custom_code_preserved(self, hybrid_builder: HybridBuilder) -> None:
        spec = hybrid_builder.build(
            "X", "Nauka", "Badacz", "Syntezy",
            custom_code="async def run(): ...",
        )
        assert "run" in spec.custom_code

    def test_tools_preserved(self, hybrid_builder: HybridBuilder) -> None:
        spec = hybrid_builder.build(
            "X", "Nauka", "Badacz", "Syntezy",
            tools=["search", "calculator"],
        )
        assert "search" in spec.tools


class TestCustomAgentStore:
    def test_add_and_get(self, custom_store: CustomAgentStore) -> None:
        spec = NoCodeBuilder().build("Test", "Medycyna", "Analityk", "Danych")
        custom_store.add(spec)
        retrieved = custom_store.get(spec.agent_id)
        assert retrieved is not None
        assert retrieved.display_name == "Test"

    def test_count(self, custom_store: CustomAgentStore) -> None:
        assert custom_store.count() == 0
        custom_store.add(NoCodeBuilder().build("A", "Prawo", "Ekspert", "Ryzyka"))
        assert custom_store.count() == 1

    def test_delete(self, custom_store: CustomAgentStore) -> None:
        spec = NoCodeBuilder().build("DeletionTestAgent", "Sport", "Coach", "Ryzyka")
        custom_store.add(spec)
        assert custom_store.delete(spec.agent_id) is True
        assert custom_store.get(spec.agent_id) is None

    def test_delete_nonexistent(self, custom_store: CustomAgentStore) -> None:
        assert custom_store.delete("nonexistent") is False

    def test_persistence(self, tmp_path) -> None:
        path = tmp_path / "persist.json"
        s1 = CustomAgentStore(path=path)
        spec = NoCodeBuilder().build("Persist", "Nauka", "Badacz", "Syntezy")
        s1.add(spec)
        # Nowa instancja – powinno wczytać z pliku
        s2 = CustomAgentStore(path=path)
        assert s2.get(spec.agent_id) is not None


# ===========================================================================
# 4. Google Auth Service
# ===========================================================================

class TestGoogleAuthService:
    def test_is_configured(self, auth_service: GoogleAuthService) -> None:
        assert auth_service.is_configured is True

    def test_unconfigured_service(self) -> None:
        service = GoogleAuthService("", "", "http://x", "secret32chars_changeme_in_prod!!")
        assert service.is_configured is False

    def test_get_authorization_url(self, auth_service: GoogleAuthService) -> None:
        from urllib.parse import urlparse
        url = auth_service.get_authorization_url(state="test123")
        parsed = urlparse(url)
        assert parsed.netloc == "accounts.google.com"
        assert "test-client-id" in url
        assert "test123" in url

    def test_create_and_verify_jwt(self, auth_service: GoogleAuthService) -> None:
        user_info = {"sub": "1234", "email": "test@example.com", "name": "Test", "picture": ""}
        token   = auth_service.create_session_jwt(user_info)
        payload = auth_service.verify_session_jwt(token)
        assert payload["email"] == "test@example.com"
        assert payload["sub"] == "1234"

    def test_expired_jwt_raises(self, auth_service: GoogleAuthService) -> None:
        import time
        # Utwórz serwis z 0-minutowym tokenem
        svc = GoogleAuthService(
            client_id="id", client_secret="sec",
            redirect_uri="http://x",
            jwt_secret="testsecretkey32charslongrequired!!",
            jwt_expire_minutes=0,
        )
        user_info = {"sub": "x", "email": "x@x.com", "name": "X", "picture": ""}
        token = svc.create_session_jwt(user_info)
        # Token wygasł (expire=0 → exp = now)
        time.sleep(1)
        with pytest.raises(Exception):
            svc.verify_session_jwt(token)

    def test_invalid_jwt_raises(self, auth_service: GoogleAuthService) -> None:
        with pytest.raises(Exception):
            auth_service.verify_session_jwt("not.a.valid.token")

    def test_demo_token(self, auth_service: GoogleAuthService) -> None:
        token   = auth_service.get_demo_token("demo@example.com")
        payload = auth_service.verify_session_jwt(token)
        assert payload["email"] == "demo@example.com"
        assert payload["sub"] == "demo-user-001"


class TestAuthAPI:
    def test_google_login_returns_info(self, client) -> None:
        r = client.get("/api/v1/auth/google")
        assert r.status_code == 200
        data = r.json()
        # Bez konfiguracji → demo mode
        assert "status" in data

    def test_demo_token(self, client) -> None:
        r = client.get("/api/v1/auth/google/demo")
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "Bearer"

    def test_me_without_token_401(self, client) -> None:
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401

    def test_me_with_valid_token(self, client) -> None:
        # Pobierz demo token, potem użyj w /me
        r1 = client.get("/api/v1/auth/google/demo?email=test@czlowiek.pl")
        token = r1.json()["access_token"]
        r2 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        assert r2.json()["email"] == "test@czlowiek.pl"

    def test_logout(self, client) -> None:
        r = client.post("/api/v1/auth/logout")
        assert r.status_code == 200
        assert r.json()["status"] == "logged_out"


# ===========================================================================
# 5. MCP Server
# ===========================================================================

class TestMcpServer:
    @pytest.mark.asyncio
    async def test_initialize(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        })
        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "test-mcp"
        assert "capabilities" in result

    @pytest.mark.asyncio
    async def test_ping(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 2,
            "method": "ping", "params": {},
        })
        assert resp["result"] == {}

    @pytest.mark.asyncio
    async def test_tools_list(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 3,
            "method": "tools/list", "params": {},
        })
        tools = resp["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "list_agents" in names
        assert "search_agents" in names
        assert "get_agent" in names
        assert "list_historical" in names
        assert "build_agent_no_code" in names
        assert "get_server_info" in names

    @pytest.mark.asyncio
    async def test_tools_call_list_agents(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 4,
            "method": "tools/call",
            "params": {"name": "list_agents", "arguments": {"limit": 5}},
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["total"] == 55555
        assert len(content["agents"]) == 5

    @pytest.mark.asyncio
    async def test_tools_call_search_agents(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 5,
            "method": "tools/call",
            "params": {"name": "search_agents", "arguments": {"query": "Medycyna", "limit": 10}},
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "count" in content
        assert "agents" in content

    @pytest.mark.asyncio
    async def test_tools_call_get_agent(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 6,
            "method": "tools/call",
            "params": {"name": "get_agent", "arguments": {"agent_id": "agent_0001"}},
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["agent_id"] == "agent_0001"

    @pytest.mark.asyncio
    async def test_tools_call_get_server_info(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 7,
            "method": "tools/call",
            "params": {"name": "get_server_info", "arguments": {}},
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["registry_size"] == 55555

    @pytest.mark.asyncio
    async def test_resources_list(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 8,
            "method": "resources/list", "params": {},
        })
        uris = [r["uri"] for r in resp["result"]["resources"]]
        assert "czlowiek-roku://agents" in uris
        assert "czlowiek-roku://historical" in uris

    @pytest.mark.asyncio
    async def test_resources_read_agents(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 9,
            "method": "resources/read",
            "params": {"uri": "czlowiek-roku://agents"},
        })
        content = json.loads(resp["result"]["contents"][0]["text"])
        assert content["total"] == 55555

    @pytest.mark.asyncio
    async def test_prompts_list(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 10,
            "method": "prompts/list", "params": {},
        })
        names = [p["name"] for p in resp["result"]["prompts"]]
        assert "agent_intro" in names
        assert "task_dispatch" in names

    @pytest.mark.asyncio
    async def test_prompts_get_agent_intro(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 11,
            "method": "prompts/get",
            "params": {"name": "agent_intro", "arguments": {"agent_id": "agent_0001", "user_name": "Jan"}},
        })
        text = resp["result"]["messages"][0]["content"]["text"]
        assert "Jan" in text

    @pytest.mark.asyncio
    async def test_unknown_method_error(self, mcp_server: McpServer) -> None:
        resp = await mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 99,
            "method": "unknown/method", "params": {},
        })
        assert "error" in resp
        assert resp["error"]["code"] == -32601  # METHOD_NOT_FOUND


class TestMcpAPI:
    def test_mcp_info(self, client) -> None:
        r = client.get("/api/v1/mcp/info")
        assert r.status_code == 200
        assert "name" in r.json()
        assert r.json()["protocol"] == "2024-11-05"

    def test_mcp_tools_list(self, client) -> None:
        r = client.get("/api/v1/mcp/tools")
        assert r.status_code == 200
        assert "tools" in r.json()

    def test_mcp_resources_list(self, client) -> None:
        r = client.get("/api/v1/mcp/resources")
        assert r.status_code == 200
        assert "resources" in r.json()

    def test_mcp_rpc_initialize(self, client) -> None:
        r = client.post("/api/v1/mcp/rpc", json={
            "jsonrpc": "2.0", "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        })
        assert r.status_code == 200
        assert "result" in r.json()

    def test_mcp_rpc_tools_list(self, client) -> None:
        r = client.post("/api/v1/mcp/rpc", json={
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/list", "params": {},
        })
        assert r.status_code == 200
        assert "tools" in r.json()["result"]


# ===========================================================================
# 6. Builder API Endpoints
# ===========================================================================

class TestBuilderAPI:
    def test_get_form_options(self, client) -> None:
        r = client.get("/api/v1/builder/options")
        assert r.status_code == 200
        data = r.json()
        assert "domains" in data
        assert "roles" in data

    def test_build_no_code_success(self, client) -> None:
        r = client.post("/api/v1/builder/no-code", json={
            "display_name":   "Testowy Agent No-Code",
            "domain":         "Medycyna",
            "role":           "Analityk",
            "specialization": "Danych",
            "category":       "specialist",
            "safety":         "safe",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["display_name"] == "Testowy Agent No-Code"
        assert data["builder_mode"] == "no_code"
        assert data["agent_id"].startswith("custom_")

    def test_build_no_code_invalid_domain(self, client) -> None:
        r = client.post("/api/v1/builder/no-code", json={
            "display_name":   "X",
            "domain":         "NIEZNANA_DOMENA",
            "role":           "Analityk",
            "specialization": "Danych",
        })
        assert r.status_code == 422

    def test_build_pro_code_success(self, client) -> None:
        r = client.post("/api/v1/builder/pro-code", json={
            "display_name":   "Pro Code Agent",
            "domain":         "Finanse",
            "role":           "Ekspert",
            "specialization": "Ryzyka",
            "mission":        "Analiza ryzyka finansowego.",
            "system_prompt":  "Jesteś ekspertem ds. ryzyka finansowego z 10-letnim doświadczeniem.",
            "category":       "specialist",
            "safety":         "safe",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["builder_mode"] == "pro_code"

    def test_build_hybrid_success(self, client) -> None:
        r = client.post("/api/v1/builder/hybrid", json={
            "display_name":          "Hybrid Agent",
            "domain":                "Prawo",
            "role":                  "Doradca",
            "specialization":        "Zgodności",
            "system_prompt_override": "Jesteś adwokatem specjalizującym się w prawie korporacyjnym.",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["builder_mode"] == "hybrid"

    def test_list_custom_agents(self, client) -> None:
        # Najpierw utwórz jednego agenta
        client.post("/api/v1/builder/no-code", json={
            "display_name": "Lista Test", "domain": "Sport",
            "role": "Coach", "specialization": "Ryzyka",
        })
        r = client.get("/api/v1/builder/agents")
        assert r.status_code == 200
        assert "total" in r.json()
        assert "agents" in r.json()
