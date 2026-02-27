// ViewModel okna czatu z agentami MAS.
// Plik: clients/desktop/ChatViewModel.cs
//
// Wzorce: MVVM, INotifyPropertyChanged, ObservableCollection,
//         async/await – UI nigdy nie jest blokowane.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;

namespace CzlowiekRoku.Desktop.MAS
{
    // ──────────────────────────────────────────────────────────────────────
    // Prosta implementacja ICommand (RelayCommand)
    // ──────────────────────────────────────────────────────────────────────

    /// <summary>Lekka implementacja ICommand przyjmująca lambda-delegaty.</summary>
    internal sealed class RelayCommand : ICommand
    {
        private readonly Func<Task> _execute;
        private readonly Func<bool>? _canExecute;
        private bool _isRunning;

        public RelayCommand(Func<Task> execute, Func<bool>? canExecute = null)
        {
            _execute = execute;
            _canExecute = canExecute;
        }

        public event EventHandler? CanExecuteChanged
        {
            add => CommandManager.RequerySuggested += value;
            remove => CommandManager.RequerySuggested -= value;
        }

        public bool CanExecute(object? parameter) => !_isRunning && (_canExecute?.Invoke() ?? true);

        public async void Execute(object? parameter)
        {
            _isRunning = true;
            CommandManager.InvalidateRequerySuggested();
            try { await _execute(); }
            finally
            {
                _isRunning = false;
                CommandManager.InvalidateRequerySuggested();
            }
        }
    }

    // ──────────────────────────────────────────────────────────────────────
    // ChatViewModel
    // ──────────────────────────────────────────────────────────────────────

    /// <summary>
    /// ViewModel okna czatu. Zarządza kolekcją wiadomości i wysyłaniem
    /// tekstu do agentów przez REST + odbiorem wyników przez WebSocket.
    /// </summary>
    public sealed class ChatViewModel : INotifyPropertyChanged, IDisposable
    {
        private readonly IMasClient _masClient;
        private string _inputText = string.Empty;
        private bool _isBusy;

        /// <summary>Kolekcja wiadomości widoczna w UI (thread-safe przez dispatcher).</summary>
        public ObservableCollection<ChatMessage> Messages { get; } = new();

        /// <summary>Tekst wpisywany przez użytkownika w polu input.</summary>
        public string InputText
        {
            get => _inputText;
            set => SetField(ref _inputText, value);
        }

        /// <summary>True gdy oczekujemy na odpowiedź – blokuje przycisk Wyślij.</summary>
        public bool IsBusy
        {
            get => _isBusy;
            private set => SetField(ref _isBusy, value);
        }

        /// <summary>Komenda przycisku "Wyślij".</summary>
        public ICommand SendCommand { get; }

        public ChatViewModel(IMasClient masClient)
        {
            _masClient = masClient;
            _masClient.AgentEventReceived += OnAgentEventReceived;
            SendCommand = new RelayCommand(
                SendMessageAsync,
                () => !string.IsNullOrWhiteSpace(InputText) && !IsBusy
            );
        }

        // ──────────────────────────────────────────────────────────────────
        // Wysyłanie wiadomości
        // ──────────────────────────────────────────────────────────────────

        private async Task SendMessageAsync()
        {
            var text = InputText.Trim();
            if (string.IsNullOrEmpty(text)) return;

            AddMessage(new ChatMessage("Ty", text, DateTime.Now, isFromUser: true));
            InputText = string.Empty;
            IsBusy = true;

            try
            {
                await _masClient.SendChatMessageAsync(text);
                // Wynik agenta dotrze przez WebSocket → OnAgentEventReceived
            }
            catch (Exception ex)
            {
                AddMessage(new ChatMessage(
                    "System",
                    $"Błąd wysyłania: {ex.Message}",
                    DateTime.Now,
                    isFromUser: false
                ));
            }
            finally
            {
                IsBusy = false;
            }
        }

        // ──────────────────────────────────────────────────────────────────
        // Odbiór odpowiedzi agentów przez WebSocket
        // ──────────────────────────────────────────────────────────────────

        private void OnAgentEventReceived(object? sender, Dictionary<string, object> e)
        {
            // Wyświetlaj tylko wyniki zadań (task_result), pomijaj heartbeaty i statusy
            if (!e.TryGetValue("type", out var typeRaw)) return;
            if (typeRaw?.ToString() != "task_result") return;

            var agentId = e.TryGetValue("sender_id", out var sid)
                ? sid?.ToString() ?? "agent"
                : "agent";

            var text = ExtractAgentReplyText(e);

            // Aktualizacja UI na wątku głównym
            Application.Current.Dispatcher.Invoke(() =>
                AddMessage(new ChatMessage(agentId, text, DateTime.Now, isFromUser: false))
            );
        }

        /// <summary>Wyciąga czytelny tekst odpowiedzi z payload-u wiadomości agenta.</summary>
        private static string ExtractAgentReplyText(Dictionary<string, object> message)
        {
            if (!message.TryGetValue("payload", out var payloadRaw)) return "(brak treści)";

            // payload może być JsonElement lub Dictionary – obsługujemy oba
            if (payloadRaw is JsonElement el)
            {
                // Spróbuj wyciągnąć story lub result.visual_description
                if (el.TryGetProperty("story", out var story))
                    return story.GetString() ?? "(historia)";
                if (el.TryGetProperty("result", out var result))
                    return result.ToString();
                return el.ToString();
            }

            if (payloadRaw is Dictionary<string, object> dict)
            {
                if (dict.TryGetValue("story", out var s)) return s?.ToString() ?? "(historia)";
                if (dict.TryGetValue("result", out var r)) return r?.ToString() ?? "(wynik)";
                return string.Join(", ", dict.Keys);
            }

            return payloadRaw?.ToString() ?? "(brak treści)";
        }

        // ──────────────────────────────────────────────────────────────────
        // Helpers
        // ──────────────────────────────────────────────────────────────────

        private void AddMessage(ChatMessage msg) => Messages.Add(msg);

        public void Dispose()
        {
            _masClient.AgentEventReceived -= OnAgentEventReceived;
        }

        // ──────────────────────────────────────────────────────────────────
        // INotifyPropertyChanged
        // ──────────────────────────────────────────────────────────────────

        public event PropertyChangedEventHandler? PropertyChanged;

        private void SetField<T>(ref T field, T value, [CallerMemberName] string? name = null)
        {
            if (EqualityComparer<T>.Default.Equals(field, value)) return;
            field = value;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
        }
    }
}
