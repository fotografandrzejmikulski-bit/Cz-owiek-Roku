// Model wiadomości czatu w oknie rozmowy z agentami.
// Plik: clients/desktop/ChatMessage.cs

using System;

namespace CzlowiekRoku.Desktop.MAS
{
    /// <summary>
    /// Reprezentuje pojedynczą wiadomość w oknie czatu.
    /// </summary>
    public sealed class ChatMessage
    {
        /// <summary>Nadawca: "Ty" lub identyfikator agenta (np. "narrative_agent").</summary>
        public string Sender { get; }

        /// <summary>Treść wiadomości do wyświetlenia.</summary>
        public string Text { get; }

        /// <summary>Czas wysłania wiadomości.</summary>
        public DateTime Timestamp { get; }

        /// <summary>Czy wiadomość pochodzi od użytkownika (aligns right in UI).</summary>
        public bool IsFromUser { get; }

        public ChatMessage(string sender, string text, DateTime timestamp, bool isFromUser)
        {
            Sender = sender;
            Text = text;
            Timestamp = timestamp;
            IsFromUser = isFromUser;
        }

        /// <summary>Wyświetlany prefiks: "Ty" lub rola agenta.</summary>
        public string DisplayLabel => $"[{Timestamp:HH:mm}] {Sender}";
    }
}
