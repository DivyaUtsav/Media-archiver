package com.mediaarchive.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mediaarchive.data.api.SeriesDto
import com.mediaarchive.data.api.ArtistDto
import com.mediaarchive.viewmodel.GalleryFilters
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll

/**
 * Shared filter panel content — used by both the desktop sidebar and the
 * Android bottom-sheet. Lives in commonMain so both targets can reference it.
 */
@Composable
fun FilterPanelContent(
    filters: GalleryFilters,
    onFiltersChanged: (GalleryFilters) -> Unit,
    availableSeries: List<SeriesDto>,
    availableArtists: List<ArtistDto>,
    availableContentRatings: List<String>,
    availableArtTypes: List<String>,
) {
    Text("Filters", style = MaterialTheme.typography.titleSmall)

    // Content Rating
    if (availableContentRatings.isNotEmpty()) {
        Text("Rating", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        availableContentRatings.forEach { rating ->
            val checked = rating in filters.contentRatings
            Row(verticalAlignment = Alignment.CenterVertically) {
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
            Row(verticalAlignment = Alignment.CenterVertically) {
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
        Column(modifier = Modifier.heightIn(max = 250.dp).verticalScroll(rememberScrollState())) {
            availableSeries.forEach { series ->
                val checked = series.id in filters.seriesIds
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = checked,
                        onCheckedChange = { on ->
                            val updated = if (on) filters.seriesIds + series.id else filters.seriesIds - series.id
                            onFiltersChanged(filters.copy(seriesIds = updated))
                        },
                    )
                    Column {
                        Text(series.name, style = MaterialTheme.typography.bodyMedium)
                        Text(
                            "${series.artworkCount} artworks",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }

    // Artists
    if (availableArtists.isNotEmpty()) {
        HorizontalDivider()
        Text("Artists", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Column(modifier = Modifier.heightIn(max = 250.dp).verticalScroll(rememberScrollState())) {
            availableArtists.forEach { artist ->
                val checked = artist.id in filters.artistIds
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = checked,
                        onCheckedChange = { on ->
                            val updated = if (on) filters.artistIds + artist.id else filters.artistIds - artist.id
                            onFiltersChanged(filters.copy(artistIds = updated))
                        },
                    )
                    Column {
                        Text(artist.name, style = MaterialTheme.typography.bodyMedium)
                        Text(
                            "${artist.artworkCount} artworks",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
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
