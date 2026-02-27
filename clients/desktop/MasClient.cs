// Klient Windows Desktop (C# / .NET 8 / WinUI 3 lub WPF)
// Plik: clients/desktop/MasClient.cs
//
// Komunikacja: HttpClient (REST) + ClientWebSocket (WebSocket)
// Asynchroniczna – UI nie blokuje się podczas oczekiwania na agentów.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace CzlowiekRoku.Desktop.MAS
{
    // ──────────────────────────────────────────────────────────────────────
    // Modele danych
    // ──────────────────────────────────────────────────────────────────────

    public record TaskRequest(
        string ClientId,
        string TaskType,
        Dictionary<string, object> Payload
    );

    public record TaskResponse(
        string TaskId,
        string Status,
        Dictionary<string, object>? Result
    );

    public record AgentInfo(
        string AgentId,
        List<string> Capabilities,
        string Status
    );

    // ──────────────────────────────────────────────────────────────────────
    // Interfejs klienta MAS (zasada Dependency Inversion – SOLID)
    // ──────────────────────────────────────────────────────────────────────

    public interface IMasClient : IDisposable
    {
        event EventHandler<Dictionary<string, object>> AgentEventReceived;
        Task ConnectAsync(CancellationToken cancellationToken = default);
        Task DisconnectAsync();
        Task<TaskResponse> SubmitTaskAsync(string taskType, Dictionary<string, object> payload);
        Task<List<AgentInfo>> ListAgentsAsync();
    }

    // ──────────────────────────────────────────────────────────────────────
    // Implementacja
    // ──────────────────────────────────────────────────────────────────────

    /// <summary>
    /// Klient systemu wieloagentowego dla desktopa Windows.
    /// Obsługuje REST (zadania) i WebSocket (wyniki w czasie rzeczywistym).
    /// </summary>
    public sealed class MasClient : IMasClient
    {
        private readonly string _baseUrl;
        private readonly string _clientId;
        private readonly HttpClient _httpClient;
        private ClientWebSocket? _webSocket;
        private CancellationTokenSource? _wsCts;

        public event EventHandler<Dictionary<string, object>>? AgentEventReceived;

        private static readonly JsonSerializerOptions JsonOptions = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
            WriteIndented = false
        };

        public MasClient(string baseUrl, string clientId)
        {
            _baseUrl = baseUrl.TrimEnd('/');
            _clientId = clientId;
            _httpClient = new HttpClient { BaseAddress = new Uri(_baseUrl) };
        }

        // ──────────────────────────────────────────────────────────────────
        // WebSocket
        // ──────────────────────────────────────────────────────────────────

        public async Task ConnectAsync(CancellationToken cancellationToken = default)
        {
            _wsCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            _webSocket = new ClientWebSocket();
            var wsUri = new Uri(_baseUrl.Replace("http", "ws") + "/ws");
            await _webSocket.ConnectAsync(wsUri, _wsCts.Token);
            _ = Task.Run(() => ReceiveLoopAsync(_wsCts.Token), _wsCts.Token);
        }

        public async Task DisconnectAsync()
        {
            _wsCts?.Cancel();
            if (_webSocket?.State == WebSocketState.Open)
                await _webSocket.CloseAsync(
                    WebSocketCloseStatus.NormalClosure, "Rozłączenie", CancellationToken.None);
        }

        private async Task ReceiveLoopAsync(CancellationToken ct)
        {
            var buffer = new byte[4096];
            while (!ct.IsCancellationRequested &&
                   _webSocket?.State == WebSocketState.Open)
            {
                try
                {
                    var result = await _webSocket.ReceiveAsync(buffer, ct);
                    if (result.MessageType == WebSocketMessageType.Text)
                    {
                        var json = Encoding.UTF8.GetString(buffer, 0, result.Count);
                        var data = JsonSerializer.Deserialize<Dictionary<string, object>>(
                            json, JsonOptions);
                        if (data != null)
                            AgentEventReceived?.Invoke(this, data);
                    }
                }
                catch (OperationCanceledException) { break; }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"[MasClient] Błąd WebSocket: {ex.Message}");
                    // Prosta strategia ponownego połączenia
                    await Task.Delay(5_000, ct);
                    try { await ConnectAsync(ct); } catch { /* ignoruj jeśli też błąd */ }
                }
            }
        }

        // ──────────────────────────────────────────────────────────────────
        // REST API
        // ──────────────────────────────────────────────────────────────────

        public async Task<TaskResponse> SubmitTaskAsync(
            string taskType,
            Dictionary<string, object> payload)
        {
            var request = new TaskRequest(_clientId, taskType, payload);
            var json = JsonSerializer.Serialize(request, JsonOptions);
            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            var response = await _httpClient.PostAsync("/api/v1/tasks/", content);
            response.EnsureSuccessStatusCode();
            var body = await response.Content.ReadAsStringAsync();
            return JsonSerializer.Deserialize<TaskResponse>(body, JsonOptions)
                   ?? throw new InvalidOperationException("Pusta odpowiedź API");
        }

        public async Task<List<AgentInfo>> ListAgentsAsync()
        {
            var body = await _httpClient.GetStringAsync("/api/v1/agents/");
            return JsonSerializer.Deserialize<List<AgentInfo>>(body, JsonOptions)
                   ?? new List<AgentInfo>();
        }

        public void Dispose()
        {
            _wsCts?.Cancel();
            _webSocket?.Dispose();
            _httpClient.Dispose();
        }
    }
}
