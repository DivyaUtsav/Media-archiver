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
    availableContentRatings: List<String>,
    availableArtTypes: List<String>,
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
                availableContentRatings = availableContentRatings,
                availableArtTypes = availableArtTypes,
            )
        }

        // Content area
        Box(modifier = Modifier.weight(1f).fillMaxHeight()) {
            content()
        }
    }
}

@Composable
fun FilterPanelContent(
    filters: GalleryFilters,
    onFiltersChanged: (GalleryFilters) -> Unit,
    availableSeries: List<SeriesDto>,
    availableContentRatings: List<String>,
    availableArtTypes: List<String>,
) {
    Text("Filters", style = MaterialTheme.typography.titleSmall)

    // Content Rating
    if (availableContentRatings.isNotEmpty()) {
        Text("Rating", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        availableContentRatings.forEach { rating ->
            val checked = rating in filters.contentRatings
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Checkbox(
                    checked = checked,
                    onCheckedChange = { on ->
                        val updated = if (on) filters.contentRatings + rating else filters.contentRatings - rating
                        onFiltersChanged(filters.copy(contentRatings = updated))
                    },
                )
                Text(rating, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }

    // Art Type
    if (availableArtTypes.isNotEmpty()) {
        HorizontalDivider()
        Text("Art Type", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        availableArtTypes.forEach { artType ->
            val checked = artType in filters.artTypes
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Checkbox(
                    checked = checked,
                    onCheckedChange = { on ->
                        val updated = if (on) filters.artTypes + artType else filters.artTypes - artType
                        onFiltersChanged(filters.copy(artTypes = updated))
                    },
                )
                Text(artType, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }

    // Series
    if (availableSeries.isNotEmpty()) {
        HorizontalDivider()
        Text("Series", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        availableSeries.forEach { series ->
            val checked = series.id in filters.seriesIds
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Checkbox(
                    checked = checked,
                    onCheckedChange = { on ->
                        val updated = if (on) filters.seriesIds + series.id else filters.seriesIds - series.id
                        onFiltersChanged(filters.copy(seriesIds = updated))
                    },
                )
                Column {
                    Text(series.name, style = MaterialTheme.typography.bodyMedium)
                    Text("${series.artworkCount} artworks", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }

    // Clear filters button
    if (filters != GalleryFilters()) {
        HorizontalDivider()
        OutlinedButton(
            onClick = { onFiltersChanged(GalleryFilters()) },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Clear Filters") }
    }
}
