package com.mediaarchive.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mediaarchive.data.api.ArtistDto
import com.mediaarchive.data.api.CharacterDto
import com.mediaarchive.data.api.SeriesDto
import com.mediaarchive.viewmodel.GalleryFilters
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.clickable

@Composable
fun FilterPanelContent(
    filters: GalleryFilters,
    onFiltersChanged: (GalleryFilters) -> Unit,
    availableSeries: List<SeriesDto>,
    availableArtists: List<ArtistDto>,
    availableContentRatings: List<String>,
    availableArtTypes: List<String>,
    seriesCharacters: Map<Int, List<CharacterDto>> = emptyMap(),
    onSeriesExpanded: (Int) -> Unit = {},
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

    // Series + Characters (hierarchical)
    if (availableSeries.isNotEmpty()) {
        HorizontalDivider()
        Text("Series", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Column(modifier = Modifier.heightIn(max = 400.dp).verticalScroll(rememberScrollState())) {
            availableSeries.forEach { series ->
                val isSeriesChecked = series.id in filters.seriesIds
                val isExpanded = series.id in filters.expandedSeriesIds
                val characters = seriesCharacters[series.id] ?: emptyList()

                // Series row
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Checkbox(
                        checked = isSeriesChecked,
                        onCheckedChange = { on ->
                            val updatedSeries = if (on) filters.seriesIds + series.id else filters.seriesIds - series.id
                            // If unchecking series, also remove its characters from filter
                            val updatedChars = if (!on) {
                                filters.characterIds.filter { charId ->
                                    characters.none { it.id == charId }
                                }
                            } else filters.characterIds
                            onFiltersChanged(filters.copy(seriesIds = updatedSeries, characterIds = updatedChars))
                        },
                    )
                    Column(modifier = Modifier.weight(1f)) {
                        Text(series.name, style = MaterialTheme.typography.bodyMedium)
                        Text(
                            "${series.artworkCount} artworks",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    // Expand/collapse toggle
                    IconButton(onClick = { onSeriesExpanded(series.id) }) {
                        Icon(
                            if (isExpanded) Icons.Default.KeyboardArrowDown
                            else Icons.Default.KeyboardArrowRight,
                            contentDescription = if (isExpanded) "Collapse" else "Expand",
                            modifier = Modifier.size(18.dp),
                        )
                    }
                }

                // Character sub-list (only when expanded)
                if (isExpanded) {
                    if (characters.isEmpty()) {
                        Box(modifier = Modifier.padding(start = 32.dp, bottom = 4.dp)) {
                            Text(
                                "Loading…",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    } else {
                        characters.forEach { character ->
                            val isCharChecked = character.id in filters.characterIds
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.padding(start = 24.dp).fillMaxWidth(),
                            ) {
                                Checkbox(
                                    checked = isCharChecked,
                                    onCheckedChange = { on ->
                                        val updated = if (on) filters.characterIds + character.id
                                        else filters.characterIds - character.id
                                        onFiltersChanged(filters.copy(characterIds = updated))
                                    },
                                )
                                Text(character.name, style = MaterialTheme.typography.bodySmall)
                            }
                        }
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
