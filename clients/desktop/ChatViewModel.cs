// ViewModel okna czatu z agentami MAS.
// Plik: clients/desktop/ChatViewModel.cs
//
// Wzorce: MVVM, INotifyPropertyChanged, ObservableCollection,
//         async/await – UI nigdy nie jest blokowane.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Linq;
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
    // Model pozycji agenta na liście
    // ──────────────────────────────────────────────────────────────────────

    public sealed class AgentListItem : INotifyPropertyChanged
    {
        private string _statusLabel = "aktywny";

        public string AgentId { get; set; } = "";
        public string Role { get; set; } = "";
        public List<string> Capabilities { get; set; } = new();

        public string StatusLabel
        {
            get => _statusLabel;
            set { _statusLabel = value; OnPropertyChanged(); }
        }

        public event PropertyChangedEventHandler? PropertyChanged;
        private void OnPropertyChanged([CallerMemberName] string? name = null)
            => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }

    // ──────────────────────────────────────────────────────────────────────
    // ChatViewModel
    // ──────────────────────────────────────────────────────────────────────

    /// <summary>
    /// ViewModel okna czatu. Zarządza kolekcją wiadomości, listą agentów
    /// i formularzem Budowniczego Agentów.
    /// </summary>
    public sealed class ChatViewModel : INotifyPropertyChanged, IDisposable
    {
        private readonly IMasClient _masClient;
        private string _inputText = string.Empty;
        private string _intentHint = string.Empty;
        private string _chatSubtitle = "Wszystkie agenty nasluchuja";
        private string _llmBackendLabel = "mock";
        private string _builderStatusMessage = string.Empty;
        private string _newAgentName = string.Empty;
        private string _newAgentRole = string.Empty;
        private string _newAgentCapabilities = string.Empty;
        private string _newAgentDescription = string.Empty;
        private string _researchProgressStatus = string.Empty;
        private bool _isBusy;
        private bool _isResearchMode;
        private RegistryDomainInfo? _selectedDomain;
        private RegistryAgentEntry? _selectedRegistryAgent;
        private string _registryChatInput = string.Empty;
        private int _domainTotalAgents;

        // ── Kolekcje ──────────────────────────────────────────────────────

        public ObservableCollection<ChatMessage>      Messages        { get; } = new();
        public ObservableCollection<AgentListItem>    ActiveAgents    { get; } = new();
        public ObservableCollection<string>           AllCapabilities { get; } = new();
        public ObservableCollection<RegistryDomainInfo>  Domains      { get; } = new();
        public ObservableCollection<RegistryAgentEntry>  DomainAgents { get; } = new();

        // ── Właściwości bindowane ──────────────────────────────────────────

        public string InputText
        {
            get => _inputText;
            set
            {
                SetField(ref _inputText, value);
                UpdateIntentHint(value);
            }
        }

        public string IntentHint               { get => _intentHint;               private set => SetField(ref _intentHint,               value); }
        public string ChatSubtitle             { get => _chatSubtitle;             private set => SetField(ref _chatSubtitle,             value); }
        public string LlmBackendLabel          { get => _llmBackendLabel;          private set => SetField(ref _llmBackendLabel,          value); }
        public string BuilderStatusMessage     { get => _builderStatusMessage;     private set => SetField(ref _builderStatusMessage,     value); }
        public string ResearchProgressStatus   { get => _researchProgressStatus;   private set => SetField(ref _researchProgressStatus,   value); }
        public string NewAgentName             { get => _newAgentName;             set => SetField(ref _newAgentName,             value); }
        public string NewAgentRole             { get => _newAgentRole;             set => SetField(ref _newAgentRole,             value); }
        public string NewAgentCapabilities     { get => _newAgentCapabilities;     set => SetField(ref _newAgentCapabilities,     value); }
        public string NewAgentDescription      { get => _newAgentDescription;      set => SetField(ref _newAgentDescription,      value); }
        public bool   IsBusy                   { get => _isBusy;                   private set => SetField(ref _isBusy,           value); }

        // ── Domain browsing properties ────────────────────────────────────

        /// <summary>Aktualnie wybrana dziedzina z listy Domains.</summary>
        public RegistryDomainInfo? SelectedDomain
        {
            get => _selectedDomain;
            set
            {
                if (SetField(ref _selectedDomain, value) && value != null)
                    _ = LoadDomainAgentsAsync(value.Domain);
            }
        }

        /// <summary>Aktualnie wybrany agent z listy DomainAgents.</summary>
        public RegistryAgentEntry? SelectedRegistryAgent
        {
            get => _selectedRegistryAgent;
            set
            {
                SetField(ref _selectedRegistryAgent, value);
                if (value != null)
                    ChatSubtitle = $"Agent: {value.DisplayName} ({value.Domain})";
            }
        }

        /// <summary>Tekst wiadomości czatu kierowanej do SelectedRegistryAgent.</summary>
        public string RegistryChatInput
        {
            get => _registryChatInput;
            set => SetField(ref _registryChatInput, value);
        }

        /// <summary>Łączna liczba agentów w aktualnie wybranej dziedzinie.</summary>
        public int DomainTotalAgents
        {
            get => _domainTotalAgents;
            private set => SetField(ref _domainTotalAgents, value);
        }

        /// <summary>True = tryb Deep Research; False = tryb czatu.</summary>
        public bool IsResearchMode
        {
            get => _isResearchMode;
            set
            {
                SetField(ref _isResearchMode, value);
                IntentHint = value
                    ? "Tryb Deep Research: Planner → Researcher(fan-out) → Critic → Writer"
                    : string.Empty;
            }
        }

        // ── Etykieta trybu dla przycisku ──────────────────────────────────
        public string SendButtonLabel => IsResearchMode ? "Badaj" : "Wyslij";

        // ── Komendy ───────────────────────────────────────────────────────

        public ICommand SendCommand             { get; }
        public ICommand BuildAgentCommand       { get; }
        public ICommand SelectAgentCommand      { get; }
        public ICommand RefreshAgentsCommand    { get; }
        public ICommand ToggleResearchMode      { get; }
        public ICommand LoadDomainsCommand      { get; }
        public ICommand RegistryChatCommand     { get; }

        // ──────────────────────────────────────────────────────────────────
        // Konstruktor
        // ──────────────────────────────────────────────────────────────────

        public ChatViewModel(IMasClient masClient, string llmBackend = "mock")
        {
            _masClient = masClient;
            _llmBackendLabel = llmBackend.ToUpperInvariant();
            _masClient.AgentEventReceived += OnAgentEventReceived;

            SendCommand = new RelayCommand(
                SendMessageAsync,
                () => !string.IsNullOrWhiteSpace(InputText) && !IsBusy
            );
            BuildAgentCommand = new RelayCommand(
                BuildAgentAsync,
                () => !string.IsNullOrWhiteSpace(NewAgentName)
                   && !string.IsNullOrWhiteSpace(NewAgentRole)
                   && !string.IsNullOrWhiteSpace(NewAgentCapabilities)
            );
            SelectAgentCommand   = new RelayCommand<string>(SelectAgent);
            RefreshAgentsCommand = new RelayCommand(RefreshAgentsAsync);
            ToggleResearchMode   = new RelayCommand(() =>
            {
                IsResearchMode = !IsResearchMode;
                OnPropertyChanged(nameof(SendButtonLabel));
                return Task.CompletedTask;
            });
            LoadDomainsCommand  = new RelayCommand(LoadDomainsAsync);
            RegistryChatCommand = new RelayCommand(
                RegistryChatSendAsync,
                () => SelectedRegistryAgent != null && !string.IsNullOrWhiteSpace(RegistryChatInput) && !IsBusy
            );

            // Powitalna wiadomosc
            AddMessage(new ChatMessage(
                "System",
                "Witaj w systemie Czlowiek Roku MAS! Mozesz pisac naturalnym jezkiem – " +
                "np. 'wygeneruj tresc o walce', 'analiza zachowan gracza' lub " +
                "wlacz tryb Deep Research i napisz pytanie badawcze. " +
                "Agenty odpowiedza przez WebSocket. " +
                "Zakładka 'Dziedziny' umozliwia przegladanie 55 555 agentow pogrupowanych w dziedziny.",
                DateTime.Now, isFromUser: false));

            // Zaladuj liste agentow i dziedzin asynchronicznie
            _ = RefreshAgentsAsync();
            _ = LoadDomainsAsync();
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
            IntentHint = string.Empty;
            IsBusy = true;

            try
            {
                if (IsResearchMode)
                {
                    ResearchProgressStatus = "Faza 1: Planowanie pytan badawczych...";
                    await _masClient.StartResearchAsync(text);
                    // Wyniki i postep dotra przez WebSocket (research_progress events)
                }
                else
                {
                    await _masClient.SendChatMessageAsync(text);
                    // Wynik agenta dotrze przez WebSocket
                }
            }
            catch (Exception ex)
            {
                AddMessage(new ChatMessage("System",
                    $"Blad wysylania: {ex.Message}", DateTime.Now, isFromUser: false));
                ResearchProgressStatus = string.Empty;
            }
            finally { IsBusy = false; }
        }

        // ──────────────────────────────────────────────────────────────────
        // Budowniczy Agentów
        // ──────────────────────────────────────────────────────────────────

        private async Task BuildAgentAsync()
        {
            var caps = NewAgentCapabilities
                .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .ToList();

            BuilderStatusMessage = string.Empty;
            IsBusy = true;
            try
            {
                var response = await _masClient.RegisterAgentAsync(
                    NewAgentName.Trim(), NewAgentRole.Trim(), caps, NewAgentDescription.Trim());

                BuilderStatusMessage = $"Agent '{response.AgentId}' uruchomiony!";
                AddMessage(new ChatMessage("System",
                    $"Nowy agent '{response.AgentId}' ({string.Join(", ", caps)}) dolaczyl do systemu.",
                    DateTime.Now, isFromUser: false));

                // Wyczyść formularz i odśwież listę
                NewAgentName = NewAgentRole = NewAgentCapabilities = NewAgentDescription = string.Empty;
                await RefreshAgentsAsync();
            }
            catch (Exception ex)
            {
                BuilderStatusMessage = $"Blad: {ex.Message}";
            }
            finally { IsBusy = false; }
        }

        // ──────────────────────────────────────────────────────────────────
        // Lista agentów
        // ──────────────────────────────────────────────────────────────────

        private async Task RefreshAgentsAsync()
        {
            try
            {
                var agents = await _masClient.ListAgentsAsync();
                Application.Current.Dispatcher.Invoke(() =>
                {
                    ActiveAgents.Clear();
                    AllCapabilities.Clear();
                    var capsSet = new HashSet<string>();

                    foreach (var a in agents)
                    {
                        ActiveAgents.Add(new AgentListItem
                        {
                            AgentId = a.AgentId,
                            Role = ExtractRole(a),
                            Capabilities = a.Capabilities,
                            StatusLabel = a.Status,
                        });
                        foreach (var c in a.Capabilities) capsSet.Add(c);
                    }
                    foreach (var c in capsSet.OrderBy(x => x))
                        AllCapabilities.Add(c);

                    ChatSubtitle = $"{agents.Count} agent(ow) aktywnych";
                });
            }
            catch { /* siec niedostepna – ignoruj */ }
        }

        private static string ExtractRole(AgentInfo agent)
            => agent.AgentId.Replace("_agent", "").Replace("_", " ");

        private Task SelectAgent(string? agentId)
        {
            if (!string.IsNullOrEmpty(agentId))
                ChatSubtitle = $"Kierujesz do: {agentId}";
            return Task.CompletedTask;
        }

        // ──────────────────────────────────────────────────────────────────
        // Podpowiedź intencji (live hint pod polem input)
        // ──────────────────────────────────────────────────────────────────

        private void UpdateIntentHint(string text)
        {
            if (string.IsNullOrWhiteSpace(text))
            {
                IntentHint = string.Empty;
                return;
            }
            var lower = text.ToLower();
            if (lower.Contains("analiz") || lower.Contains("statystyki"))
                IntentHint = "Intencja: Analityka gracza -> AnalyticsAgent";
            else if (lower.Contains("tresc") || lower.Contains("wygeneruj") || lower.Contains("historia"))
                IntentHint = "Intencja: Generowanie tresci -> NarrativeAgent + ContentAgent";
            else
                IntentHint = "Intencja: Generowanie tresci (domyslnie)";
        }

        // ──────────────────────────────────────────────────────────────────
        // Odbiór odpowiedzi agentów przez WebSocket
        // ──────────────────────────────────────────────────────────────────

        private void OnAgentEventReceived(object? sender, Dictionary<string, object> e)
        {
            if (!e.TryGetValue("type", out var typeRaw)) return;
            var msgType = typeRaw?.ToString() ?? "";

            // Research progress events (broadcast type)
            if (e.TryGetValue("event", out var eventRaw) &&
                eventRaw?.ToString() == "research_progress")
            {
                HandleResearchProgress(e);
                return;
            }

            if (msgType != "task_result") return;

            var agentId = e.TryGetValue("sender_id", out var sid) ? sid?.ToString() ?? "agent" : "agent";
            var text = ExtractAgentReplyText(e);

            Application.Current.Dispatcher.Invoke(() =>
                AddMessage(new ChatMessage(agentId, text, DateTime.Now, isFromUser: false))
            );
        }

        private void HandleResearchProgress(Dictionary<string, object> e)
        {
            var status = e.TryGetValue("status", out var s) ? s?.ToString() ?? "" : "";
            var iteration = e.TryGetValue("iteration", out var it)
                ? Convert.ToInt32(it) : 0;
            var quality = e.TryGetValue("quality_score", out var q)
                ? Convert.ToInt32(q) : 0;
            var report = e.TryGetValue("final_report", out var r) ? r?.ToString() ?? "" : "";

            var statusLabel = status switch
            {
                "planning"    => "Faza 1: Planner - dekompozycja pytania...",
                "researching" => $"Faza 2: Researcher (iteracja {iteration + 1}) - przeszukiwanie rownolegle...",
                "reflecting"  => $"Faza 3: Critic - ocena jakosci (iteracja {iteration})...",
                "writing"     => "Faza 4: Writer - synteza raportu...",
                "done"        => $"Raport gotowy! Jakosc: {quality}/100",
                "error"       => "Blad podczas badania",
                _             => status,
            };

            Application.Current.Dispatcher.Invoke(() =>
            {
                ResearchProgressStatus = statusLabel;
                if (status == "done" && !string.IsNullOrEmpty(report))
                {
                    ResearchProgressStatus = string.Empty;
                    AddMessage(new ChatMessage(
                        $"deep_research [{quality}/100]",
                        report,
                        DateTime.Now,
                        isFromUser: false
                    ));
                }
            });
        }

        private static string ExtractAgentReplyText(Dictionary<string, object> message)
        {
            if (!message.TryGetValue("payload", out var payloadRaw)) return "(brak tresci)";
            if (payloadRaw is JsonElement el)
            {
                if (el.TryGetProperty("story", out var story))   return story.GetString() ?? "(historia)";
                if (el.TryGetProperty("result", out var result)) return result.ToString();
                if (el.TryGetProperty("pipeline_results", out var pr)) return pr.ToString();
                return el.ToString();
            }
            if (payloadRaw is Dictionary<string, object> dict)
            {
                if (dict.TryGetValue("story", out var s))  return s?.ToString() ?? "(historia)";
                if (dict.TryGetValue("result", out var r)) return r?.ToString() ?? "(wynik)";
            }
            return payloadRaw?.ToString() ?? "(brak tresci)";
        }

        // ──────────────────────────────────────────────────────────────────
        // Przeglądanie dziedzin (55 555 agentów rejestru)
        // ──────────────────────────────────────────────────────────────────

        private async Task LoadDomainsAsync()
        {
            try
            {
                // Ładuj dziedziny strona po stronie (maks. 500 na raz)
                int offset = 0;
                const int pageSize = 500;
                Application.Current.Dispatcher.Invoke(() => Domains.Clear());

                while (true)
                {
                    var page = await _masClient.GetDomainsAsync(offset, pageSize);
                    Application.Current.Dispatcher.Invoke(() =>
                    {
                        foreach (var d in page.Domains)
                            Domains.Add(d);
                    });
                    if (offset + pageSize >= page.TotalDomains) break;
                    offset += pageSize;
                }
            }
            catch { /* siec niedostepna – ignoruj */ }
        }

        private async Task LoadDomainAgentsAsync(string domain)
        {
            try
            {
                IsBusy = true;
                Application.Current.Dispatcher.Invoke(() => DomainAgents.Clear());

                int offset = 0;
                const int pageSize = 100;

                while (true)
                {
                    var page = await _masClient.GetAgentsByDomainAsync(domain, offset, pageSize);
                    DomainTotalAgents = page.Total;
                    Application.Current.Dispatcher.Invoke(() =>
                    {
                        foreach (var a in page.Agents)
                            DomainAgents.Add(a);
                    });
                    if (offset + pageSize >= page.Total) break;
                    offset += pageSize;
                }
            }
            catch { /* siec niedostepna – ignoruj */ }
            finally { IsBusy = false; }
        }

        private async Task RegistryChatSendAsync()
        {
            if (SelectedRegistryAgent == null || string.IsNullOrWhiteSpace(RegistryChatInput))
                return;

            var agent = SelectedRegistryAgent;
            var text  = RegistryChatInput.Trim();

            AddMessage(new ChatMessage("Ty", text, DateTime.Now, isFromUser: true));
            RegistryChatInput = string.Empty;
            IsBusy = true;

            try
            {
                var reply = await _masClient.RegistryChatAsync(agent.AgentId, text);
                AddMessage(new ChatMessage(
                    $"{reply.DisplayName} [{reply.Domain}]",
                    reply.Reply,
                    DateTime.Now,
                    isFromUser: false));
            }
            catch (Exception ex)
            {
                AddMessage(new ChatMessage("System",
                    $"Blad czatu z agentem: {ex.Message}", DateTime.Now, isFromUser: false));
            }
            finally { IsBusy = false; }
        }

        // ──────────────────────────────────────────────────────────────────
        // Helpers
        // ──────────────────────────────────────────────────────────────────

        private void AddMessage(ChatMessage msg) => Messages.Add(msg);

        public void Dispose()
        {
            _masClient.AgentEventReceived -= OnAgentEventReceived;
        }

        // ── INotifyPropertyChanged ─────────────────────────────────────────

        public event PropertyChangedEventHandler? PropertyChanged;

        private bool SetField<T>(ref T field, T value, [CallerMemberName] string? name = null)
        {
            if (EqualityComparer<T>.Default.Equals(field, value)) return false;
            field = value;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
            return true;
        }

        private void OnPropertyChanged(string name)
            => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }

    // ──────────────────────────────────────────────────────────────────────
    // RelayCommand<T> – parametryzowany
    // ──────────────────────────────────────────────────────────────────────

    internal sealed class RelayCommand<T> : ICommand
    {
        private readonly Func<T?, Task> _execute;
        public RelayCommand(Func<T?, Task> execute) => _execute = execute;

        public event EventHandler? CanExecuteChanged
        {
            add => CommandManager.RequerySuggested += value;
            remove => CommandManager.RequerySuggested -= value;
        }

        public bool CanExecute(object? parameter) => true;
        public async void Execute(object? parameter) => await _execute((T?)parameter);
    }
}
