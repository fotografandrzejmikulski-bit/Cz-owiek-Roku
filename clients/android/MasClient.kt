// Klient Android (Kotlin / Jetpack Compose + Coroutines + OkHttp WebSocket)
// Plik: clients/android/MasClient.kt
//
// Architektura:
//   ViewModel -> MasClient -> WebSocket/REST -> MAS Backend
//   (asynchroniczna komunikacja, UI nigdy nie jest blokowane)

package pl.czlowiekroku.client.android

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

// ─────────────────────────────────────────────────────────────────────────────
// Modele danych
// ─────────────────────────────────────────────────────────────────────────────

@Serializable
data class TaskRequest(
    val client_id: String,
    val task_type: String,
    val payload: Map<String, String> = emptyMap()
)

@Serializable
data class TaskResponse(
    val task_id: String,
    val status: String,
    val result: Map<String, String>? = null
)

@Serializable
data class AgentStatusUpdate(
    val agent_id: String,
    val role: String,
    val status: String
)

// ─────────────────────────────────────────────────────────────────────────────
// Klient MAS (WebSocket + REST)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Klient systemu wieloagentowego dla Androida.
 *
 * Obsługuje:
 *  - asynchroniczne zlecanie zadań (REST POST /api/v1/tasks)
 *  - odbiór wyników w czasie rzeczywistym przez WebSocket
 *  - automatyczne ponowne połączenie po utracie łączności
 */
class MasClient(
    private val baseUrl: String,
    private val clientId: String,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.IO)
) {
    private val TAG = "MasClient"
    private val json = Json { ignoreUnknownKeys = true }
    private val mediaTypeJson = "application/json; charset=utf-8".toMediaType()

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS) // bez timeoutu dla WebSocket
        .build()

    // SharedFlow do obserwacji wyników przez ViewModel/UI
    private val _agentEvents = MutableSharedFlow<Map<String, String>>(extraBufferCapacity = 64)
    val agentEvents: SharedFlow<Map<String, String>> = _agentEvents

    private var webSocket: WebSocket? = null

    // ──────────────────────────────────────────────────────────────────────
    // WebSocket
    // ──────────────────────────────────────────────────────────────────────

    /** Nawiąż połączenie WebSocket z backendem MAS. */
    fun connect() {
        val request = Request.Builder()
            .url("${baseUrl.replace("http", "ws")}/ws")
            .build()

        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "WebSocket połączony z $baseUrl")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                scope.launch {
                    try {
                        val event = json.decodeFromString<Map<String, String>>(text)
                        _agentEvents.emit(event)
                    } catch (e: Exception) {
                        Log.e(TAG, "Błąd parsowania wiadomości WS: ${e.message}")
                    }
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "Błąd WebSocket: ${t.message}. Ponowne połączenie za 5s...")
                scope.launch {
                    kotlinx.coroutines.delay(5_000)
                    connect()
                }
            }
        })
    }

    fun disconnect() {
        webSocket?.close(1000, "Rozłączenie klienta")
        webSocket = null
    }

    // ──────────────────────────────────────────────────────────────────────
    // REST API
    // ──────────────────────────────────────────────────────────────────────

    /**
     * Zleć zadanie orkiestratorowi.
     * Wynik przyjdzie asynchronicznie przez [agentEvents].
     */
    suspend fun submitTask(taskType: String, payload: Map<String, String> = emptyMap()): TaskResponse {
        val request = TaskRequest(
            client_id = clientId,
            task_type = taskType,
            payload = payload
        )
        val body = json.encodeToString(request).toRequestBody(mediaTypeJson)
        val httpRequest = Request.Builder()
            .url("$baseUrl/api/v1/tasks/")
            .post(body)
            .build()

        return httpClient.newCall(httpRequest).execute().use { response ->
            if (!response.isSuccessful) error("Błąd HTTP ${response.code}")
            json.decodeFromString(response.body!!.string())
        }
    }

    /** Pobierz listę aktywnych agentów z ich statusami. */
    suspend fun listAgents(): List<AgentStatusUpdate> {
        val httpRequest = Request.Builder()
            .url("$baseUrl/api/v1/agents/")
            .get()
            .build()

        return httpClient.newCall(httpRequest).execute().use { response ->
            if (!response.isSuccessful) error("Błąd HTTP ${response.code}")
            json.decodeFromString(response.body!!.string())
        }
    }
}
