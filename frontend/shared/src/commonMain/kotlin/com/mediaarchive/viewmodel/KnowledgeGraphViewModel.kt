package com.mediaarchive.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mediaarchive.data.api.ApiClient
import com.mediaarchive.data.api.ArtistDto
import com.mediaarchive.data.api.CharacterDto
import com.mediaarchive.data.api.SeriesDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class KgSeriesItem(
    val series: SeriesDto,
    val isExpanded: Boolean = false,
    val characters: List<KgCharacterItem> = emptyList(),
    val isLoadingCharacters: Boolean = false,
)

data class KgCharacterItem(
    val character: CharacterDto,
    val artworkCount: Int = 0,
)

data class KnowledgeGraphState(
    val series: List<KgSeriesItem> = emptyList(),
    val characters: List<CharacterDto> = emptyList(),
    val artists: List<ArtistDto> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null,
    val seriesSearch: String = "",
    val characterSearch: String = "",
    val artistSearch: String = "",
    val pendingDeleteSeries: SeriesDto? = null,
    val pendingDeleteCharacter: CharacterDto? = null,
    val pendingDeleteCharacterArtworkCount: Int = 0,
    val pendingDeleteArtist: ArtistDto? = null,
    val pendingDeleteArtistArtworkCount: Int = 0,
    val actionError: String? = null,
)

class KnowledgeGraphViewModel(private val api: ApiClient) : ViewModel() {

    private val _state = MutableStateFlow(KnowledgeGraphState())
    val state: StateFlow<KnowledgeGraphState> = _state

    init { loadAll() }

    fun loadAll() {
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null)
            try {
                val seriesResult = api.getSeries()
                val artistResult = api.getArtists(limit = 500)
                _state.value = _state.value.copy(
                    isLoading = false,
                    series = seriesResult.items.map { KgSeriesItem(series = it) },
                    artists = artistResult.items,
                )
                loadCharacters()
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }

    private fun loadCharacters() {
        viewModelScope.launch {
            runCatching { api.getAllCharacters() }.onSuccess { result ->
                _state.value = _state.value.copy(characters = result.items)
            }
        }
    }

    // ── Series ────────────────────────────────────────────────────────────

    fun toggleSeriesExpanded(seriesId: Int) {
        val current = _state.value.series
        val index = current.indexOfFirst { it.series.id == seriesId }
        if (index < 0) return
        val item = current[index]
        if (item.isExpanded) {
            _state.value = _state.value.copy(
                series = current.toMutableList().also {
                    it[index] = item.copy(isExpanded = false)
                }
            )
        } else {
            _state.value = _state.value.copy(
                series = current.toMutableList().also {
                    it[index] = item.copy(isExpanded = true, isLoadingCharacters = true)
                }
            )
            loadSeriesCharacters(seriesId)
        }
    }

    private fun loadSeriesCharacters(seriesId: Int) {
        viewModelScope.launch {
            runCatching { api.getSeriesCharacters(seriesId) }.onSuccess { result ->
                val current = _state.value.series
                val index = current.indexOfFirst { it.series.id == seriesId }
                if (index < 0) return@onSuccess
                _state.value = _state.value.copy(
                    series = current.toMutableList().also {
                        it[index] = it[index].copy(
                            isLoadingCharacters = false,
                            characters = result.characters.map { c ->
                                KgCharacterItem(
                                    character = CharacterDto(
                                        id = c.id,
                                        name = c.name,
                                        seriesId = seriesId,
                                    ),
                                    artworkCount = c.artworkCount,
                                )
                            }
                        )
                    }
                )
            }.onFailure {
                val current = _state.value.series
                val index = current.indexOfFirst { it.series.id == seriesId }
                if (index < 0) return@onFailure
                _state.value = _state.value.copy(
                    series = current.toMutableList().also {
                        it[index] = it[index].copy(isLoadingCharacters = false)
                    }
                )
            }
        }
    }

    fun renameSeries(seriesId: Int, newName: String) {
        viewModelScope.launch {
            runCatching { api.updateSeries(seriesId, newName) }.onSuccess { response ->
                _state.value = _state.value.copy(
                    series = _state.value.series.map {
                        if (it.series.id == seriesId) it.copy(series = it.series.copy(name = response.name))
                        else it
                    },
                    actionError = null,
                )
            }.onFailure {
                _state.value = _state.value.copy(actionError = it.message)
            }
        }
    }

    fun requestDeleteSeries(series: SeriesDto) {
        _state.value = _state.value.copy(pendingDeleteSeries = series, actionError = null)
    }

    fun cancelDelete() {
        _state.value = _state.value.copy(
            pendingDeleteSeries = null,
            pendingDeleteCharacter = null,
            pendingDeleteArtist = null,
            actionError = null,
        )
    }

    fun confirmDeleteSeries() {
        val series = _state.value.pendingDeleteSeries ?: return
        viewModelScope.launch {
            runCatching { api.deleteSeries(series.id) }.onSuccess {
                _state.value = _state.value.copy(
                    series = _state.value.series.filter { it.series.id != series.id },
                    pendingDeleteSeries = null,
                    actionError = null,
                )
            }.onFailure {
                _state.value = _state.value.copy(
                    pendingDeleteSeries = null,
                    actionError = it.message,
                )
            }
        }
    }

    // ── Characters ────────────────────────────────────────────────────────

    fun renameCharacter(characterId: Int, newName: String, seriesId: Int) {
        viewModelScope.launch {
            runCatching { api.updateCharacter(characterId, name = newName) }.onSuccess {
                refreshCharacterInSeries(seriesId, characterId, newName)
                _state.value = _state.value.copy(actionError = null)
            }.onFailure {
                _state.value = _state.value.copy(actionError = it.message)
            }
        }
    }

    fun moveCharacter(characterId: Int, newSeriesId: Int, oldSeriesId: Int) {
        viewModelScope.launch {
            runCatching { api.updateCharacter(characterId, seriesId = newSeriesId) }.onSuccess {
                // Remove from old series characters list and refresh
                removeCharacterFromSeries(oldSeriesId, characterId)
                loadSeriesCharacters(newSeriesId)
                _state.value = _state.value.copy(actionError = null)
            }.onFailure {
                _state.value = _state.value.copy(actionError = it.message)
            }
        }
    }

    fun requestDeleteCharacter(character: CharacterDto, artworkCount: Int) {
        _state.value = _state.value.copy(
            pendingDeleteCharacter = character,
            pendingDeleteCharacterArtworkCount = artworkCount,
            actionError = null,
        )
    }

    fun confirmDeleteCharacter() {
        val character = _state.value.pendingDeleteCharacter ?: return
        viewModelScope.launch {
            runCatching { api.deleteCharacter(character.id) }.onSuccess {
                removeCharacterFromSeries(character.seriesId ?: -1, character.id)
                _state.value = _state.value.copy(
                    pendingDeleteCharacter = null,
                    actionError = null,
                )
            }.onFailure {
                _state.value = _state.value.copy(
                    pendingDeleteCharacter = null,
                    actionError = it.message,
                )
            }
        }
    }

    private fun refreshCharacterInSeries(seriesId: Int, characterId: Int, newName: String) {
        val series = _state.value.series.toMutableList()
        val index = series.indexOfFirst { it.series.id == seriesId }
        if (index < 0) return
        val item = series[index]
        series[index] = item.copy(
            characters = item.characters.map {
                if (it.character.id == characterId) it.copy(character = it.character.copy(name = newName))
                else it
            }
        )
        _state.value = _state.value.copy(series = series)
    }

    private fun removeCharacterFromSeries(seriesId: Int, characterId: Int) {
        val series = _state.value.series.toMutableList()
        val index = series.indexOfFirst { it.series.id == seriesId }
        if (index < 0) return
        val item = series[index]
        series[index] = item.copy(characters = item.characters.filter { it.character.id != characterId })
        _state.value = _state.value.copy(series = series)
    }

    // ── Artists ───────────────────────────────────────────────────────────

    fun renameArtist(artistId: Int, newName: String) {
        viewModelScope.launch {
            runCatching { api.updateArtist(artistId, newName) }.onSuccess { response ->
                _state.value = _state.value.copy(
                    artists = _state.value.artists.map {
                        if (it.id == artistId) it.copy(name = response.name) else it
                    },
                    actionError = null,
                )
            }.onFailure {
                _state.value = _state.value.copy(actionError = it.message)
            }
        }
    }

    fun requestDeleteArtist(artist: ArtistDto) {
        _state.value = _state.value.copy(
            pendingDeleteArtist = artist,
            pendingDeleteArtistArtworkCount = artist.artworkCount,
            actionError = null,
        )
    }

    fun confirmDeleteArtist() {
        val artist = _state.value.pendingDeleteArtist ?: return
        viewModelScope.launch {
            runCatching { api.deleteArtist(artist.id) }.onSuccess {
                _state.value = _state.value.copy(
                    artists = _state.value.artists.filter { it.id != artist.id },
                    pendingDeleteArtist = null,
                    actionError = null,
                )
            }.onFailure {
                _state.value = _state.value.copy(
                    pendingDeleteArtist = null,
                    actionError = it.message,
                )
            }
        }
    }

    fun updateSeriesSearch(query: String) {
        _state.value = _state.value.copy(seriesSearch = query)
    }

    fun updateCharacterSearch(query: String) {
        _state.value = _state.value.copy(characterSearch = query)
    }

    fun updateArtistSearch(query: String) {
        _state.value = _state.value.copy(artistSearch = query)
    }
}