// Code-behind okna czatu – inicjalizacja, auto-scroll, Enter jako Wyślij.
// Plik: clients/desktop/ChatWindow.xaml.cs

using System;
using System.Collections.Specialized;
using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;

namespace CzlowiekRoku.Desktop.MAS
{
    // ──────────────────────────────────────────────────────────────────────
    // Konwerter: bool (IsFromUser) → Visibility
    //   ConverterParameter="Visible"  → Visible gdy IsFromUser==true
    //   ConverterParameter="Collapsed" → Visible gdy IsFromUser==false
    // ──────────────────────────────────────────────────────────────────────

    [ValueConversion(typeof(bool), typeof(Visibility))]
    public sealed class BoolToAlignmentConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            var isFromUser = value is bool b && b;
            var showWhenUser = parameter?.ToString() == "Visible";
            return (isFromUser == showWhenUser) ? Visibility.Visible : Visibility.Collapsed;
        }

        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotSupportedException();
    }

    // ──────────────────────────────────────────────────────────────────────
    // Selektor stylu bąbelka (nie używany bezpośrednio w XAML w tej wersji,
    // ale dostępny do rozszerzenia)
    // ──────────────────────────────────────────────────────────────────────

    public sealed class ChatBubbleStyleSelector : StyleSelector
    {
        public Style? UserStyle { get; set; }
        public Style? AgentStyle { get; set; }

        public override Style? SelectStyle(object item, DependencyObject container)
        {
            if (item is ChatMessage msg)
                return msg.IsFromUser ? UserStyle : AgentStyle;
            return base.SelectStyle(item, container);
        }
    }

    // ──────────────────────────────────────────────────────────────────────
    // ChatWindow – code-behind
    // ──────────────────────────────────────────────────────────────────────

    /// <summary>
    /// Okno czatu z agentami MAS.
    ///
    /// Użycie:
    /// <code>
    ///   var masClient = new MasClient("http://localhost:8000", "desktop-1");
    ///   await masClient.ConnectAsync();
    ///   var window = new ChatWindow(masClient);
    ///   window.Show();
    /// </code>
    /// </summary>
    public partial class ChatWindow : Window
    {
        private readonly ChatViewModel _viewModel;

        public ChatWindow(IMasClient masClient)
        {
            InitializeComponent();
            _viewModel = new ChatViewModel(masClient);
            DataContext = _viewModel;

            // Auto-scroll gdy pojawia się nowa wiadomość
            _viewModel.Messages.CollectionChanged += OnMessagesChanged;
        }

        // ──────────────────────────────────────────────────────────────────
        // Auto-scroll do końca listy po dodaniu wiadomości
        // ──────────────────────────────────────────────────────────────────

        private void OnMessagesChanged(object? sender, NotifyCollectionChangedEventArgs e)
        {
            if (e.Action == NotifyCollectionChangedAction.Add)
            {
                Dispatcher.InvokeAsync(() =>
                    MessagesScroll.ScrollToBottom(),
                    System.Windows.Threading.DispatcherPriority.Background
                );
            }
        }

        // ──────────────────────────────────────────────────────────────────
        // Enter wysyła wiadomość (Shift+Enter = nowa linia, nie używane tu)
        // ──────────────────────────────────────────────────────────────────

        private void InputBox_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.Key == Key.Enter && _viewModel.SendCommand.CanExecute(null))
            {
                _viewModel.SendCommand.Execute(null);
                e.Handled = true;
            }
        }

        protected override void OnClosed(EventArgs e)
        {
            _viewModel.Dispose();
            _viewModel.Messages.CollectionChanged -= OnMessagesChanged;
            base.OnClosed(e);
        }
    }
}
