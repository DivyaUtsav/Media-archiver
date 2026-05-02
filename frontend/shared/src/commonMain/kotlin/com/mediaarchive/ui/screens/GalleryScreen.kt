package com.mediaarchive.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mediaarchive.data.AppContainer
import com.mediaarchive.ui.FilterContainer
import com.mediaarchive.ui.components.ArtworkCard
import com.mediaarchive.ui.theme.AccentTeal
import com.mediaarchive.ui.theme.RatingNSFW
import com.mediaarchive.viewmodel.GalleryFilters
import com.mediaarchive.viewmodel.GalleryViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GalleryScreen(
    viewModel: GalleryViewModel,
    onArtworkClick: (Int) -> Unit,
    onQueueClick: () -> Unit,
    onSettingsClick: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val gridState = rememberLazyGridState()

    // Pagination trigger — load more when near the end
    LaunchedEffect(gridState.firstVisibleItemIndex, gridState.layoutInfo.totalItemsCount) {
        val total = gridState.layoutInfo.totalItemsCount
        val last = gridState.firstVisibleItemIndex + gridState.layoutInfo.visibleItemsInfo.size
        if (total > 0 && last >= total - 6) viewModel.loadMore()
    }

    FilterContainer(
        filters = state.filters,
        onFiltersChanged = viewModel::updateFilters,
        availableSeries = state.availableSeries,
        availableContentRatings = state.availableContentRatings,
        availableArtTypes = state.availableArtTypes,
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text("Archive", style = MaterialTheme.typography.titleLarge) },
                    actions = {
                        // Queue badge
                        IconButton(onClick = onQueueClick) {
                            BadgedBox(badge = {
                                if (state.queueCount > 0) Badge {
                                    Text("${state.queueCount}")
                                }
                            }) {
                                Icon(
                                    Icons.Default.CheckCircle,
                                    contentDescription = "Review Queue (${state.queueCount})",
                                    tint = if (state.queueCount > 0) RatingNSFW else AccentTeal,
                                )
                            }
                        }
                        IconButton(onClick = viewModel::loadInitial) {
                            Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                        }
                        IconButton(onClick = onSettingsClick) {
                            Icon(Icons.Default.Settings, contentDescription = "Settings")
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.surface,
                    ),
                )
            },
        ) { padding ->
            Box(modifier = Modifier.padding(padding).fillMaxSize()) {
                when {
                    state.isLoading -> {
                        CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                    }
                    state.error != null -> {
                        Column(
                            modifier = Modifier.align(Alignment.Center),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            Text("Could not connect to archive", style = MaterialTheme.typography.titleMedium)
                            Text(state.error ?: "", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Button(onClick = viewModel::loadInitial) { Text("Retry") }
                        }
                    }
                    state.artworks.isEmpty() -> {
                        Text(
                            "No artworks match the current filters.",
                            modifier = Modifier.align(Alignment.Center),
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    else -> {
                        LazyVerticalGrid(
                            columns = GridCells.Adaptive(minSize = 200.dp),
                            state = gridState,
                            contentPadding = PaddingValues(8.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.fillMaxSize(),
                        ) {
                            items(state.artworks, key = { it.id }) { artwork ->
                                ArtworkCard(
                                    artwork = artwork,
                                    mediaUrl = AppContainer.apiClient.mediaUrl(artwork.id),
                                    onClick = { onArtworkClick(artwork.id) },
                                )
                            }
                            if (state.isLoadingMore) {
                                item(span = { GridItemSpan(maxLineSpan) }) {
                                    Box(modifier = Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                                        CircularProgressIndicator()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
