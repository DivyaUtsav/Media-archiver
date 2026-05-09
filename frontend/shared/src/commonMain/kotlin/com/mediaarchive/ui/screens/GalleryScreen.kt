package com.mediaarchive.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.List
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.mediaarchive.data.AppContainer
import com.mediaarchive.ui.FilterContainer
import com.mediaarchive.ui.components.ArtworkCard
import com.mediaarchive.ui.onEscapeKey
import com.mediaarchive.ui.onEnterOrEscape
import com.mediaarchive.ui.theme.AccentTeal
import com.mediaarchive.ui.theme.RatingNSFW
import com.mediaarchive.viewmodel.GalleryFilters
import com.mediaarchive.viewmodel.GalleryViewModel
import com.mediaarchive.viewmodel.AvailableArtTypes
import com.mediaarchive.viewmodel.AvailableContentRatings
import kotlinx.coroutines.delay


@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GalleryScreen(
    viewModel: GalleryViewModel,
    onArtworkClick: (Int) -> Unit,
    onQueueClick: () -> Unit,
    onSettingsClick: () -> Unit,
    onKnowledgeGraphClick: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val gridState = rememberLazyGridState()

    var searchQuery by remember { mutableStateOf("") }
    var searchActive by remember { mutableStateOf(false) }

    LaunchedEffect(searchQuery) {
        delay(300)
        viewModel.updateSearch(searchQuery)
        viewModel.loadInitial()
    }

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
        availableArtists = state.availableArtists,
        availableContentRatings = AvailableContentRatings,
        availableArtTypes = AvailableArtTypes,
        seriesCharacters = state.seriesCharacters,
        onSeriesExpanded = viewModel::toggleSeriesExpanded,
    ) {
        var showBulkEditDialog by remember { mutableStateOf(false) }
        var showBulkDeleteConfirm by remember { mutableStateOf(false) }

        Scaffold(
            modifier = Modifier.onEscapeKey {
                when {
                    searchActive -> { searchActive = false; searchQuery = "" }
                    state.selectionMode -> viewModel.clearSelection()
                }
            },
            topBar = {
                if (state.selectionMode) {
                    TopAppBar(
                        title = { Text("${state.selectedArtworkIds.size} selected") },
                        navigationIcon = {
                            IconButton(onClick = viewModel::clearSelection) {
                                Icon(Icons.Default.Close, contentDescription = "Clear selection") // Using refresh as a clear icon for now
                            }
                        },
                        actions = {
                            IconButton(onClick = viewModel::selectAll) {
                                Icon(Icons.Default.CheckCircle, contentDescription = "Select All")
                            }
                            Button(
                                onClick = { showBulkEditDialog = true },
                                enabled = state.selectedArtworkIds.isNotEmpty(),
                                modifier = Modifier.padding(end = 4.dp)
                            ) {
                                Text("Edit Tags")
                            }
                            IconButton(
                                onClick = { showBulkDeleteConfirm = true },
                                enabled = state.selectedArtworkIds.isNotEmpty(),
                            ) {
                                Icon(
                                    Icons.Default.Delete,
                                    contentDescription = "Delete selected",
                                    tint = if (state.selectedArtworkIds.isNotEmpty()) MaterialTheme.colorScheme.error
                                    else MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        },
                        colors = TopAppBarDefaults.topAppBarColors(
                            containerColor = MaterialTheme.colorScheme.primaryContainer,
                            titleContentColor = MaterialTheme.colorScheme.onPrimaryContainer
                        ),
                    )
                } else {
                    TopAppBar(
                        title = {
                            if (searchActive) {
                                OutlinedTextField(
                                    value = searchQuery,
                                    onValueChange = { searchQuery = it },
                                    placeholder = { Text("Search artworks…") },
                                    singleLine = true,
                                    modifier = Modifier.fillMaxWidth().padding(end = 8.dp),
                                    textStyle = MaterialTheme.typography.bodyMedium,
                                    trailingIcon = {
                                        if (searchQuery.isNotEmpty()) {
                                            IconButton(onClick = { searchQuery = "" }) {
                                                Icon(Icons.Default.Clear, contentDescription = "Clear search")
                                            }
                                        }
                                    },
                                )
                            } else {
                                Text("Archive", style = MaterialTheme.typography.titleLarge)
                            }
                        },
                        actions = {
                            IconButton(onClick = {
                                searchActive = !searchActive
                                if (!searchActive) searchQuery = ""
                            }) {
                                Icon(
                                    if (searchActive) Icons.Default.Clear else Icons.Default.Search,
                                    contentDescription = if (searchActive) "Close search" else "Search",
                                )
                            }
                            IconButton(onClick = onKnowledgeGraphClick) {
                                Icon(Icons.Default.List, contentDescription = "Knowledge Graph")
                            }
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
                }
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
                                    onClick = {
                                        if (state.selectionMode) viewModel.toggleSelection(artwork.id)
                                        else onArtworkClick(artwork.id)
                                    },
                                    onLongClick = {
                                        if (!state.selectionMode) viewModel.toggleSelectionMode()
                                        viewModel.toggleSelection(artwork.id)
                                    },
                                    isSelected = state.selectedArtworkIds.contains(artwork.id)
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

            if (showBulkEditDialog) {
                BulkEditDialog(
                    onDismiss = { showBulkEditDialog = false },
                    onConfirm = { request ->
                        viewModel.bulkUpdateTags(
                            request.copy(artworkIds = state.selectedArtworkIds.toList()),
                            onSuccess = { showBulkEditDialog = false }
                        )
                    },
                    isSaving = state.isBulkUpdating,
                    saveError = state.bulkUpdateError
                )
            }

            if (showBulkDeleteConfirm) {
                AlertDialog(
                    onDismissRequest = { if (!state.isBulkUpdating) showBulkDeleteConfirm = false },
                    modifier = Modifier.onEnterOrEscape(
                        onEnter = { if (!state.isBulkUpdating) viewModel.bulkDelete(onSuccess = { showBulkDeleteConfirm = false }) },
                        onEscape = { if (!state.isBulkUpdating) showBulkDeleteConfirm = false },
                    ),
                    title = { Text("Delete ${state.selectedArtworkIds.size} artworks?") },
                    text = {
                        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("This will permanently delete the selected artworks and their files. This cannot be undone.")
                            state.bulkUpdateError?.let {
                                Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    },
                    confirmButton = {
                        Button(
                            onClick = { viewModel.bulkDelete(onSuccess = { showBulkDeleteConfirm = false }) },
                            enabled = !state.isBulkUpdating,
                            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                        ) {
                            if (state.isBulkUpdating) CircularProgressIndicator(modifier = Modifier.size(16.dp))
                            else Text("Delete")
                        }
                    },
                    dismissButton = {
                        OutlinedButton(
                            onClick = { showBulkDeleteConfirm = false },
                            enabled = !state.isBulkUpdating,
                        ) { Text("Cancel") }
                    }
                )
            }
        }
    }
}

@Composable
fun BulkEditDialog(
    onDismiss: () -> Unit,
    onConfirm: (com.mediaarchive.data.api.ArtworkBulkPatchRequest) -> Unit,
    isSaving: Boolean,
    saveError: String?,
) {
    var contentRating by remember { mutableStateOf<String?>(null) }
    var artType by remember { mutableStateOf<String?>(null) }
    var characterQuery by remember { mutableStateOf("") }
    var characterResults by remember { mutableStateOf<List<com.mediaarchive.data.api.CharacterTagDto>>(emptyList()) }
    var artistQuery by remember { mutableStateOf("") }
    var artistResults by remember { mutableStateOf<List<com.mediaarchive.data.api.ArtistTagDto>>(emptyList()) }
    var characters by remember { mutableStateOf<List<com.mediaarchive.data.api.CharacterTagDto>>(emptyList()) }
    var artists by remember { mutableStateOf<List<com.mediaarchive.data.api.ArtistTagDto>>(emptyList()) }

    val api = AppContainer.apiClient

    LaunchedEffect(characterQuery) {
        if (characterQuery.length >= 2) {
            delay(300)
            runCatching { api.searchCharacters(characterQuery) }.onSuccess {
                characterResults = it.items.map { c ->
                    com.mediaarchive.data.api.CharacterTagDto(id = c.id, name = c.name, series = c.series ?: com.mediaarchive.data.api.SeriesDto(0, "Unknown"), confidence = null, isManual = true)
                }
            }
        } else characterResults = emptyList()
}

    LaunchedEffect(artistQuery) {
        if (artistQuery.length >= 2) {
            delay(300)
            runCatching { api.searchArtists(artistQuery) }.onSuccess {
                artistResults = it.items.map { a -> com.mediaarchive.data.api.ArtistTagDto(id = a.id, name = a.name, confidence = null, isManual = true) }
            }
        } else artistResults = emptyList()
    }

    AlertDialog(
        onDismissRequest = { if (!isSaving) onDismiss() },
        title = { Text("Bulk Edit Tags") },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                Text("Select tags to apply to all selected artworks.", style = MaterialTheme.typography.bodyMedium)

                // Rating
                com.mediaarchive.ui.components.RatingSelector(selected = contentRating, onSelected = { contentRating = it })

                // Art Type
                com.mediaarchive.ui.components.ArtTypeSelector(selected = artType, onSelected = { artType = it })

                // Characters
                com.mediaarchive.ui.components.SearchableDropdown(
                    label = "Add character...",
                    query = characterQuery,
                    onQueryChange = { characterQuery = it },
                    results = characterResults,
                    onSelect = { c -> characters = characters + c; characterQuery = "" },
                    itemLabel = { "${it.name} · ${it.series.name}" }
                )
                if (characters.isNotEmpty()) {
                    Text("Characters to add: ${characters.joinToString { it.name }}", style = MaterialTheme.typography.labelSmall)
                }

                // Artists
                com.mediaarchive.ui.components.SearchableDropdown(
                    label = "Add artist...",
                    query = artistQuery,
                    onQueryChange = { artistQuery = it },
                    results = artistResults,
                    onSelect = { a -> artists = artists + a; artistQuery = "" },
                    itemLabel = { it.name }
                )
                if (artists.isNotEmpty()) {
                    Text("Artists to add: ${artists.joinToString { it.name }}", style = MaterialTheme.typography.labelSmall)
                }

                saveError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onConfirm(com.mediaarchive.data.api.ArtworkBulkPatchRequest(
                        artworkIds = emptyList(), // Filled by caller
                        contentRating = contentRating,
                        artType = artType,
                        characters = if (characters.isNotEmpty()) characters.map { it.id } else null,
                        artists = if (artists.isNotEmpty()) artists.map { it.id } else null,
                    ))
                },
                enabled = !isSaving && (contentRating != null || artType != null || characters.isNotEmpty() || artists.isNotEmpty())
            ) {
                if (isSaving) CircularProgressIndicator(modifier = Modifier.size(16.dp)) else Text("Apply")
            }
        },
        dismissButton = {
            OutlinedButton(onClick = onDismiss, enabled = !isSaving) { Text("Cancel") }
        }
    )
}
