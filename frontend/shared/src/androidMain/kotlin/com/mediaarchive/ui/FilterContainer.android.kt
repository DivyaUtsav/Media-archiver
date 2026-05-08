package com.mediaarchive.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mediaarchive.data.api.ArtistDto
import com.mediaarchive.data.api.CharacterDto
import com.mediaarchive.data.api.SeriesDto
import com.mediaarchive.viewmodel.GalleryFilters

@OptIn(ExperimentalMaterial3Api::class)
@Composable
actual fun FilterContainer(
    filters: GalleryFilters,
    onFiltersChanged: (GalleryFilters) -> Unit,
    availableSeries: List<SeriesDto>,
    availableArtists: List<ArtistDto>,
    availableContentRatings: List<String>,
    availableArtTypes: List<String>,
    seriesCharacters: Map<Int, List<CharacterDto>>,
    onSeriesExpanded: (Int) -> Unit,
    content: @Composable () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var showSheet by remember { mutableStateOf(false) }

    val activeFilterCount = filters.seriesIds.size +
        filters.characterIds.size +
        filters.contentRatings.size +
        filters.artTypes.size +
        filters.artistIds.size

    Box(modifier = Modifier.fillMaxSize()) {
        content()

        FloatingActionButton(
            onClick = { showSheet = true },
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(bottom = 24.dp, end = 16.dp),
            containerColor = MaterialTheme.colorScheme.primary,
        ) {
            BadgedBox(badge = {
                if (activeFilterCount > 0) Badge { Text("$activeFilterCount") }
            }) {
                Icon(Icons.Default.Menu, contentDescription = "Filters")
            }
        }
    }

    if (showSheet) {
        ModalBottomSheet(
            onDismissRequest = { showSheet = false },
            sheetState = sheetState,
            dragHandle = {
                // Custom drag handle with title
                Column(
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    BottomSheetDefaults.DragHandle()
                    Text(
                        "Filters",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                    if (activeFilterCount > 0) {
                        Text(
                            "$activeFilterCount active",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
            },
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .navigationBarsPadding()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp)
                    .padding(bottom = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
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
                Spacer(Modifier.height(8.dp))
                if (activeFilterCount > 0) {
                    OutlinedButton(
                        onClick = { onFiltersChanged(GalleryFilters()) },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Clear All Filters") }
                }
                Button(
                    onClick = { showSheet = false },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Apply") }
            }
        }
    }
}