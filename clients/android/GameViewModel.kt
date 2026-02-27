// ViewModel dla głównego ekranu gry (Jetpack Compose / Android)
// Plik: clients/android/GameViewModel.kt
//
// Wzorce: MVVM, StateFlow, Coroutines

package pl.czlowiekroku.client.android

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class GameUiState(
    val isLoading: Boolean = false,
    val agentResults: List<Map<String, String>> = emptyList(),
    val errorMessage: String? = null
)

class GameViewModel(
    private val masClient: MasClient
) : ViewModel() {

    private val _uiState = MutableStateFlow(GameUiState())
    val uiState: StateFlow<GameUiState> = _uiState

    init {
        masClient.connect()
        observeAgentEvents()
    }

    private fun observeAgentEvents() {
        viewModelScope.launch {
            masClient.agentEvents.collect { event ->
                // Aktualizuj UI – tylko na wątku głównym (StateFlow gwarantuje bezpieczeństwo)
                _uiState.value = _uiState.value.copy(
                    agentResults = _uiState.value.agentResults + event
                )
            }
        }
    }

    /** Wyślij żądanie generowania treści do systemu MAS. */
    fun generateContent(theme: String) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, errorMessage = null)
            try {
                masClient.submitTask(
                    taskType = "generate_content",
                    payload = mapOf("theme" to theme)
                )
                // Wynik dotrze przez WebSocket – UI zaktualizuje się w observeAgentEvents()
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(errorMessage = e.message)
            } finally {
                _uiState.value = _uiState.value.copy(isLoading = false)
            }
        }
    }

    override fun onCleared() {
        masClient.disconnect()
        super.onCleared()
    }
}
