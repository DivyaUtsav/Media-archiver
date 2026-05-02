package com.mediaarchive.ui

import androidx.compose.runtime.Composable
import com.mediaarchive.data.api.SeriesDto
import com.mediaarchive.viewmodel.GalleryFilters

/**
 * Android stub — just renders the content directly.
 * Bottom-sheet implementation deferred to the Android commit.
 */
@Composable
actual fun FilterContainer(
    filters: GalleryFilters,
    onFiltersChanged: (GalleryFilters) -> Unit,
    availableSeries: List<SeriesDto>,
    availableContentRatings: List<String>,
    availableArtTypes: List<String>,
    content: @Composable () -> Unit,
) {
    content()
}
