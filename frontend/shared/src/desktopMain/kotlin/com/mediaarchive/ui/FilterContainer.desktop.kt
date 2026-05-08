package com.mediaarchive.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mediaarchive.data.api.SeriesDto
import com.mediaarchive.ui.theme.Surface800
import com.mediaarchive.viewmodel.GalleryFilters

/** Desktop actual — persistent sidebar on the left, content fills the rest. */
@Composable
actual fun FilterContainer(
    filters: GalleryFilters,
    onFiltersChanged: (GalleryFilters) -> Unit,
    availableSeries: List<SeriesDto>,
    availableArtists: List<com.mediaarchive.data.api.ArtistDto>,
    availableContentRatings: List<String>,
    availableArtTypes: List<String>,
    seriesCharacters: Map<Int, List<com.mediaarchive.data.api.CharacterDto>>,
    onSeriesExpanded: (Int) -> Unit,
    content: @Composable () -> Unit,
) {
    Row(modifier = Modifier.fillMaxSize()) {
        // Sidebar
        Column(
            modifier = Modifier
                .width(260.dp)
                .fillMaxHeight()
                .background(Surface800)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            FilterPanelContent(
                filters = filters,
                onFiltersChanged = onFiltersChanged,
                availableSeries = availableSeries,
                availableArtists = availableArtists,
                availableContentRatings = availableContentRatings,
                availableArtTypes = availableArtTypes,
                seriesCharacters = seriesCharacters,
                onSeriesExpanded = onSeriesExpanded,
            )
        }

        // Content area
        Box(modifier = Modifier.weight(1f).fillMaxHeight()) {
            content()
        }
    }
}
