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
import com.mediaarchive.data.api.SeriesDto
import com.mediaarchive.viewmodel.GalleryFilters

/**
 * Android actual — renders content directly, with a floating filter FAB
 * that opens a Modal Bottom Sheet containing the filter panel.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
actual fun FilterContainer(
    filters: GalleryFilters,
    onFiltersChanged: (GalleryFilters) -> Unit,
    availableSeries: List<SeriesDto>,
    availableContentRatings: List<String>,
    availableArtTypes: List<String>,
    content: @Composable () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var showSheet by remember { mutableStateOf(false) }
    val activeFilterCount = filters.seriesIds.size +
            filters.characterIds.size +
            filters.contentRatings.size +
            filters.artTypes.size

    Box(modifier = Modifier.fillMaxSize()) {
        content()

        // Filter FAB — bottom-end of the screen
        FloatingActionButton(
            onClick = { showSheet = true },
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(16.dp),
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
        ) {
            Column(modifier = Modifier.padding(16.dp).navigationBarsPadding().verticalScroll(rememberScrollState())) {
                // Reuse the shared desktop filter panel content
                com.mediaarchive.ui.FilterPanelContent(
                    filters = filters,
                    onFiltersChanged = onFiltersChanged,
                    availableSeries = availableSeries,
                    availableContentRatings = availableContentRatings,
                    availableArtTypes = availableArtTypes,
                )
                Spacer(Modifier.height(16.dp))
                Button(
                    onClick = { showSheet = false },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Apply") }
            }
        }
    }
}
