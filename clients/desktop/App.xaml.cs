// Punkt wejścia aplikacji WPF – Człowiek Roku Desktop
// Plik: clients/desktop/App.xaml.cs
//
// Odczytuje konfigurację backendu ze zmiennych środowiskowych:
//   MASAPI_URL       – adres REST API (domyślnie http://localhost:8000)
//   MASAPI_CLIENT_ID – identyfikator klienta (domyślnie desktop_user)
//   MASAPI_BACKEND   – etykieta backendu LLM, wyświetlana w UI (domyślnie mock)

using System;
using System.Windows;

namespace CzlowiekRoku.Desktop.MAS
{
    /// <summary>
    /// Klasa główna aplikacji WPF.
    /// Tworzy <see cref="MasClient"/> na podstawie zmiennych środowiskowych
    /// i uruchamia <see cref="ChatWindow"/> z właściwym DataContext.
    /// </summary>
    public partial class App : Application
    {
        private MasClient? _masClient;

        protected override void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);

            var apiUrl   = Environment.GetEnvironmentVariable("MASAPI_URL")       ?? "http://localhost:8000";
            var clientId = Environment.GetEnvironmentVariable("MASAPI_CLIENT_ID") ?? "desktop_user";
            var backend  = Environment.GetEnvironmentVariable("MASAPI_BACKEND")   ?? "mock";

            _masClient = new MasClient(apiUrl, clientId);

            var viewModel = new ChatViewModel(_masClient, backend);
            var window    = new ChatWindow { DataContext = viewModel };

            MainWindow = window;
            window.Show();

            // Nawiąż połączenie WebSocket w tle – nie blokuj UI
            _ = _masClient.ConnectAsync();
        }

        protected override void OnExit(ExitEventArgs e)
        {
            _masClient?.Dispose();
            base.OnExit(e);
        }
    }
}
