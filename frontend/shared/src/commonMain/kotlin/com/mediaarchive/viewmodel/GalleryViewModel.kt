package com.mediaarchive.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mediaarchive.data.api.ApiClient
import com.mediaarchive.data.api.ArtworkSummaryDto
import com.mediaarchive.data.api.SeriesDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class GalleryFilters(
    val seriesIds: List<Int> = emptyList(),
    val characterIds: List<Int> = emptyList(),
    val contentRatings: List<String> = emptyList(),
    val artTypes: List<String> = emptyList(),
)

data class GalleryState(
    val artworks: List<ArtworkSummaryDto> = emptyList(),
    val isLoading: Boolean = false,
    val isLoadingMore: Boolean = false,
    val currentPage: Int = 1,
    val hasMore: Boolean = true,
    val filters: GalleryFilters = GalleryFilters(),
    val availableSeries: List<SeriesDto> = emptyList(),
    val queueCount: Int = 0,
    val error: String? = null,
) {
    val availableContentRatings = listOf("SFW", "Suggestive", "NSFW")
    val availableArtTypes = listOf("Artwork", "Cosplay", "AI Generated")
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
                val seriesResult = api.getSeries()
                val f = _state.value.filters
                val page = api.getArtworks(
                    page = 1,
                    seriesIds = f.seriesIds,
                    characterIds = f.characterIds,
                    contentRatings = f.contentRatings,
                    artTypes = f.artTypes,
                )
                val queueCount = api.getQueueCount()
                _state.value = _state.value.copy(
                    isLoading = false,
                    artworks = page.items,
                    currentPage = 1,
                    hasMore = page.items.size < page.total,
                    availableSeries = seriesResult.items,
                    queueCount = queueCount.count,
                )
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
                    contentRatings = f.contentRatings,
                    artTypes = f.artTypes,
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
}
