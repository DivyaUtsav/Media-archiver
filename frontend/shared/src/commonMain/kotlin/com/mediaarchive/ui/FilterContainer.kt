package com.mediaarchive.ui

import androidx.compose.runtime.Composable
import com.mediaarchive.data.api.SeriesDto
import com.mediaarchive.viewmodel.GalleryFilters

/**
 * Platform-adapted filter container per LLD §4.5.
 * Desktop actual: persistent left sidebar.
 * Android actual: stub passthrough (bottom sheet in Android commit).
 */
@Composable
expect fun FilterContainer(
    filters: GalleryFilters,
    onFiltersChanged: (GalleryFilters) -> Unit,
    availableSeries: List<SeriesDto>,
    availableArtists: List<com.mediaarchive.data.api.ArtistDto>,
    availableContentRatings: List<String>,
    availableArtTypes: List<String>,
    seriesCharacters: Map<Int, List<com.mediaarchive.data.api.CharacterDto>> = emptyMap(),
    onSeriesExpanded: (Int) -> Unit = {},
    content: @Composable () -> Unit,
)
