package com.mediaarchive.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mediaarchive.data.api.ApiClient
import com.mediaarchive.data.api.ArtworkSummaryDto
import com.mediaarchive.data.api.SeriesDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope

data class GalleryFilters(
    val seriesIds: List<Int> = emptyList(),
    val characterIds: List<Int> = emptyList(),
    val artistIds: List<Int> = emptyList(),
    val contentRatings: List<String> = emptyList(),
    val artTypes: List<String> = emptyList(),
    val expandedSeriesIds: Set<Int> = emptySet(),
    val search: String = "",
)

val AvailableContentRatings = listOf("SFW", "Suggestive", "NSFW")
val AvailableArtTypes = listOf("Artwork", "Cosplay", "AI Generated")

data class GalleryState(
    val artworks: List<ArtworkSummaryDto> = emptyList(),
    val isLoading: Boolean = false,
    val isLoadingMore: Boolean = false,
    val currentPage: Int = 1,
    val hasMore: Boolean = true,
    val filters: GalleryFilters = GalleryFilters(),
    val availableSeries: List<SeriesDto> = emptyList(),
    val availableArtists: List<com.mediaarchive.data.api.ArtistDto> = emptyList(),
    val seriesCharacters: Map<Int, List<com.mediaarchive.data.api.CharacterDto>> = emptyMap(),
    val queueCount: Int = 0,
    val error: String? = null,
    val selectionMode: Boolean = false,
    val selectedArtworkIds: Set<Int> = emptySet(),
    val isBulkUpdating: Boolean = false,
    val bulkUpdateError: String? = null,
) {
}

class GalleryViewModel(private val api: ApiClient) : ViewModel() {

    private val _state = MutableStateFlow(GalleryState())
    val state: StateFlow<GalleryState> = _state

    init {
        loadInitial()
    }

    fun loadInitial() {
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null, artworks = emptyList(), currentPage = 1, hasMore = true)
            try {
                val f = _state.value.filters
                coroutineScope {
                    val seriesDeferred = async { api.getSeries() }
                    val artistDeferred = async { api.getArtists() }
                    val pageDeferred = async {
                        api.getArtworks(
                            page = 1,
                            seriesIds = f.seriesIds,
                            characterIds = f.characterIds,
                            artistIds = f.artistIds,
                            contentRatings = f.contentRatings,
                            artTypes = f.artTypes,
                            search = f.search,
                        )
                    }
                    val queueDeferred = async { api.getQueueCount() }

                    val seriesResult = seriesDeferred.await()
                    val artistResult = artistDeferred.await()
                    val page = pageDeferred.await()
                    val queueCount = queueDeferred.await()
                    _state.value = _state.value.copy(
                        isLoading = false,
                        artworks = page.items,
                        currentPage = 1,
                        hasMore = page.items.size < page.total,
                        availableSeries = seriesResult.items,
                        availableArtists = artistResult.items,
                        queueCount = queueCount.count,
                    )
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }

    fun loadMore() {
        val s = _state.value
        if (s.isLoadingMore || !s.hasMore) return
        viewModelScope.launch {
            _state.value = s.copy(isLoadingMore = true)
            try {
                val nextPage = s.currentPage + 1
                val f = s.filters
                val page = api.getArtworks(
                    page = nextPage,
                    seriesIds = f.seriesIds,
                    characterIds = f.characterIds,
                    artistIds = f.artistIds,
                    contentRatings = f.contentRatings,
                    artTypes = f.artTypes,
                    search = f.search,
                )
                _state.value = _state.value.copy(
                    isLoadingMore = false,
                    artworks = _state.value.artworks + page.items,
                    currentPage = nextPage,
                    hasMore = (_state.value.artworks.size + page.items.size) < page.total,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoadingMore = false, error = e.message)
            }
        }
    }

    fun updateFilters(filters: GalleryFilters) {
        _state.value = _state.value.copy(filters = filters)
        loadInitial()
    }

    fun toggleSeriesExpanded(seriesId: Int) {
        val current = _state.value.filters
        val expanded = current.expandedSeriesIds
        val newExpanded = if (seriesId in expanded) expanded - seriesId else expanded + seriesId
        _state.value = _state.value.copy(filters = current.copy(expandedSeriesIds = newExpanded))
        if (seriesId !in expanded && seriesId !in _state.value.seriesCharacters) {
            loadSeriesCharacters(seriesId)
        }
    }

    fun updateSearch(query: String) {
        _state.value = _state.value.copy(filters = _state.value.filters.copy(search = query))
    }

    private fun loadSeriesCharacters(seriesId: Int) {
        viewModelScope.launch {
            runCatching { api.getSeriesCharacters(seriesId) }.onSuccess { result ->
                _state.value = _state.value.copy(
                    seriesCharacters = _state.value.seriesCharacters + (seriesId to result.characters)
                )
            }
        }
    }

    fun filterBySeries(seriesId: Int) {
        _state.value = _state.value.copy(
            filters = GalleryFilters(seriesIds = listOf(seriesId))
        )
        loadInitial()
    }

    fun removeArtwork(id: Int) {
        val s = _state.value
        _state.value = s.copy(artworks = s.artworks.filter { it.id != id })
    }

    fun toggleSelectionMode() {
        val s = _state.value
        if (s.selectionMode) {
            _state.value = s.copy(selectionMode = false, selectedArtworkIds = emptySet())
        } else {
            _state.value = s.copy(selectionMode = true)
        }
    }

    fun toggleSelection(artworkId: Int) {
        val s = _state.value
        if (!s.selectionMode) return
        val newSet = if (s.selectedArtworkIds.contains(artworkId)) {
            s.selectedArtworkIds - artworkId
        } else {
            s.selectedArtworkIds + artworkId
        }
        _state.value = s.copy(selectedArtworkIds = newSet)
        if (newSet.isEmpty()) toggleSelectionMode()
    }

    fun selectAll() {
        val s = _state.value
        _state.value = s.copy(selectedArtworkIds = s.artworks.map { it.id }.toSet())
    }

    fun clearSelection() {
        _state.value = _state.value.copy(selectedArtworkIds = emptySet(), selectionMode = false)
    }

    fun bulkUpdateTags(request: com.mediaarchive.data.api.ArtworkBulkPatchRequest, onSuccess: () -> Unit) {
        viewModelScope.launch {
            _state.value = _state.value.copy(isBulkUpdating = true, bulkUpdateError = null)
            try {
                api.bulkUpdateTags(request)
                _state.value = _state.value.copy(isBulkUpdating = false, selectionMode = false, selectedArtworkIds = emptySet())
                loadInitial()
                onSuccess()
            } catch (e: Exception) {
                _state.value = _state.value.copy(isBulkUpdating = false, bulkUpdateError = e.message)
            }
        }
    }

    fun bulkDelete(onSuccess: () -> Unit) {
        val ids = _state.value.selectedArtworkIds.toList()
        viewModelScope.launch {
            _state.value = _state.value.copy(isBulkUpdating = true, bulkUpdateError = null)
            try {
                ids.forEach { api.deleteArtwork(it) }
                _state.value = _state.value.copy(
                    isBulkUpdating = false,
                    selectionMode = false,
                    selectedArtworkIds = emptySet(),
                    artworks = _state.value.artworks.filter { it.id !in ids },
                )
                onSuccess()
            } catch (e: Exception) {
                _state.value = _state.value.copy(isBulkUpdating = false, bulkUpdateError = e.message)
            }
        }
    }
}
