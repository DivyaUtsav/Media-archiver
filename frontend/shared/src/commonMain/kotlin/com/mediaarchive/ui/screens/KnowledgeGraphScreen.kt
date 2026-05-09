package com.mediaarchive.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.unit.dp
import com.mediaarchive.data.api.ArtistDto
import com.mediaarchive.data.api.CharacterDto
import com.mediaarchive.data.api.SeriesDto
import com.mediaarchive.ui.onEnterOrEscape
import com.mediaarchive.ui.onEscapeKey
import com.mediaarchive.ui.theme.OnSurfaceMuted
import com.mediaarchive.ui.theme.RatingNSFW
import com.mediaarchive.ui.theme.Surface700
import com.mediaarchive.viewmodel.KgCharacterItem
import com.mediaarchive.viewmodel.KgSeriesItem
import com.mediaarchive.viewmodel.KnowledgeGraphViewModel
import kotlinx.coroutines.delay

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun KnowledgeGraphScreen(
    viewModel: KnowledgeGraphViewModel,
    onBack: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    var selectedTab by remember { mutableStateOf(0) }
    val tabs = listOf("Series", "Artists")

    // Delete confirmation dialogs
    state.pendingDeleteSeries?.let { series ->
        AlertDialog(
            onDismissRequest = viewModel::cancelDelete,
            modifier = Modifier.onEnterOrEscape(
                onEnter = viewModel::confirmDeleteSeries,
                onEscape = viewModel::cancelDelete,
            ),
            title = { Text("Delete Series") },
            text = { Text("Delete \"${series.name}\"? This cannot be undone.") },
            confirmButton = {
                Button(
                    onClick = viewModel::confirmDeleteSeries,
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                ) { Text("Delete") }
            },
            dismissButton = {
                OutlinedButton(onClick = viewModel::cancelDelete) { Text("Cancel") }
            },
        )
    }

    state.pendingDeleteCharacter?.let { character ->
        val count = state.pendingDeleteCharacterArtworkCount
        AlertDialog(
            onDismissRequest = viewModel::cancelDelete,
            modifier = Modifier.onEnterOrEscape(
                onEnter = viewModel::confirmDeleteCharacter,
                onEscape = viewModel::cancelDelete,
            ),
            title = { Text("Delete Character") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Delete \"${character.name}\"?")
                    if (count > 0) {
                        Text(
                            "This will remove the character tag from $count artwork(s).",
                            color = RatingNSFW,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            },
            confirmButton = {
                Button(
                    onClick = viewModel::confirmDeleteCharacter,
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                ) { Text("Delete") }
            },
            dismissButton = {
                OutlinedButton(onClick = viewModel::cancelDelete) { Text("Cancel") }
            },
        )
    }

    state.pendingDeleteArtist?.let { artist ->
        val count = state.pendingDeleteArtistArtworkCount
        AlertDialog(
            onDismissRequest = viewModel::cancelDelete,
            modifier = Modifier.onEnterOrEscape(
                onEnter = viewModel::confirmDeleteArtist,
                onEscape = viewModel::cancelDelete,
            ),
            title = { Text("Delete Artist") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Delete \"${artist.name}\"?")
                    if (count > 0) {
                        Text(
                            "This will remove the artist tag from $count artwork(s).",
                            color = RatingNSFW,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            },
            confirmButton = {
                Button(
                    onClick = viewModel::confirmDeleteArtist,
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                ) { Text("Delete") }
            },
            dismissButton = {
                OutlinedButton(onClick = viewModel::cancelDelete) { Text("Cancel") }
            },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Knowledge Graph") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
    ) { padding ->
        Column(modifier = Modifier.padding(padding).fillMaxSize()) {
            // Error banner
            state.actionError?.let {
                Surface(color = MaterialTheme.colorScheme.errorContainer) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            modifier = Modifier.weight(1f),
                        )
                        IconButton(onClick = viewModel::cancelDelete) {
                            Icon(Icons.Default.Close, contentDescription = "Dismiss")
                        }
                    }
                }
            }

            TabRow(selectedTabIndex = selectedTab) {
                tabs.forEachIndexed { index, title ->
                    Tab(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        text = { Text(title) },
                    )
                }
            }

            when {
                state.isLoading -> Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                state.error != null -> Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(state.error ?: "")
                        Button(onClick = viewModel::loadAll) { Text("Retry") }
                    }
                }
                else -> when (selectedTab) {
                    0 -> SeriesTab(state.series, state.seriesSearch, viewModel)
                    1 -> ArtistsTab(state.artists, state.artistSearch, viewModel)
                }
            }
        }
    }
}

// ── Series tab ────────────────────────────────────────────────────────────────

@Composable
private fun SeriesTab(
    series: List<KgSeriesItem>,
    search: String,
    viewModel: KnowledgeGraphViewModel,
) {
    var searchQuery by remember { mutableStateOf(search) }
    LaunchedEffect(searchQuery) {
        delay(300)
        viewModel.updateSeriesSearch(searchQuery)
    }

    val filtered = remember(series, searchQuery) {
        if (searchQuery.isBlank()) series
        else series.filter { it.series.name.contains(searchQuery, ignoreCase = true) }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = searchQuery,
            onValueChange = { searchQuery = it },
            placeholder = { Text("Search series…") },
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            singleLine = true,
            trailingIcon = {
                if (searchQuery.isNotEmpty()) {
                    IconButton(onClick = { searchQuery = "" }) {
                        Icon(Icons.Default.Close, contentDescription = "Clear")
                    }
                }
            },
        )
        Text(
            "${filtered.size} series",
            style = MaterialTheme.typography.labelSmall,
            color = OnSurfaceMuted,
            modifier = Modifier.padding(horizontal = 16.dp).padding(bottom = 8.dp),
        )
        LazyColumn(modifier = Modifier.fillMaxSize()) {
            items(filtered, key = { it.series.id }) { item ->
                SeriesRow(item = item, viewModel = viewModel)
                HorizontalDivider(color = Surface700)
            }
        }
    }
}

@Composable
private fun SeriesRow(
    item: KgSeriesItem,
    viewModel: KnowledgeGraphViewModel,
) {
    val series = item.series
    var isEditing by remember(series.id) { mutableStateOf(false) }
    var editName by remember(series.name) { mutableStateOf(series.name) }
    val focusRequester = remember { FocusRequester() }

    LaunchedEffect(isEditing) {
        if (isEditing) runCatching { focusRequester.requestFocus() }
    }

    Column {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { viewModel.toggleSeriesExpanded(series.id) }
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // Expand/collapse icon
            Icon(
                if (item.isExpanded) Icons.Default.KeyboardArrowDown
                else Icons.Default.KeyboardArrowRight,
                contentDescription = null,
                modifier = Modifier.size(20.dp),
                tint = OnSurfaceMuted,
            )

            // Name — inline edit or display
            if (isEditing) {
                OutlinedTextField(
                    value = editName,
                    onValueChange = { editName = it },
                    singleLine = true,
                    modifier = Modifier
                        .weight(1f)
                        .focusRequester(focusRequester)
                        .onEnterOrEscape(
                            onEnter = {
                                if (editName.isNotBlank() && editName != series.name) {
                                    viewModel.renameSeries(series.id, editName)
                                }
                                isEditing = false
                            },
                            onEscape = {
                                editName = series.name
                                isEditing = false
                            },
                        ),
                    textStyle = MaterialTheme.typography.bodyMedium,
                )
            } else {
                Column(modifier = Modifier.weight(1f)) {
                    Text(series.name, style = MaterialTheme.typography.bodyMedium)
                    Text(
                        "${series.characterCount} characters · ${series.artworkCount} artworks",
                        style = MaterialTheme.typography.labelSmall,
                        color = OnSurfaceMuted,
                    )
                }
            }

            // Actions
            if (!isEditing) {
                IconButton(
                    onClick = { isEditing = true },
                    modifier = Modifier.size(36.dp),
                ) {
                    Icon(Icons.Default.Edit, contentDescription = "Rename", modifier = Modifier.size(18.dp))
                }
                IconButton(
                    onClick = { viewModel.requestDeleteSeries(series) },
                    modifier = Modifier.size(36.dp),
                ) {
                    Icon(
                        Icons.Default.Delete,
                        contentDescription = "Delete",
                        tint = MaterialTheme.colorScheme.error,
                        modifier = Modifier.size(18.dp),
                    )
                }
            } else {
                IconButton(
                    onClick = {
                        if (editName.isNotBlank() && editName != series.name) {
                            viewModel.renameSeries(series.id, editName)
                        }
                        isEditing = false
                    },
                    modifier = Modifier.size(36.dp),
                ) {
                    Icon(Icons.Default.Check, contentDescription = "Save", modifier = Modifier.size(18.dp), tint = MaterialTheme.colorScheme.primary)
                }
                IconButton(
                    onClick = { editName = series.name; isEditing = false },
                    modifier = Modifier.size(36.dp),
                ) {
                    Icon(Icons.Default.Close, contentDescription = "Cancel", modifier = Modifier.size(18.dp))
                }
            }
        }

        // Expanded characters
        if (item.isExpanded) {
            when {
                item.isLoadingCharacters -> Box(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(24.dp), strokeWidth = 2.dp)
                }
                item.characters.isEmpty() -> Text(
                    "No characters",
                    style = MaterialTheme.typography.bodySmall,
                    color = OnSurfaceMuted,
                    modifier = Modifier.padding(start = 48.dp, bottom = 8.dp),
                )
                else -> item.characters.forEach { charItem ->
                    CharacterRow(
                        item = charItem,
                        seriesId = series.id,
                        allSeries = emptyList(), // pass if you want move-to-series
                        viewModel = viewModel,
                    )
                }
            }
        }
    }
}

@Composable
private fun CharacterRow(
    item: KgCharacterItem,
    seriesId: Int,
    allSeries: List<SeriesDto>,
    viewModel: KnowledgeGraphViewModel,
) {
    val character = item.character
    var isEditing by remember(character.id) { mutableStateOf(false) }
    var editName by remember(character.name) { mutableStateOf(character.name) }
    val focusRequester = remember { FocusRequester() }

    LaunchedEffect(isEditing) {
        if (isEditing) runCatching { focusRequester.requestFocus() }
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 48.dp, end = 16.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (isEditing) {
            OutlinedTextField(
                value = editName,
                onValueChange = { editName = it },
                singleLine = true,
                modifier = Modifier
                    .weight(1f)
                    .focusRequester(focusRequester)
                    .onEnterOrEscape(
                        onEnter = {
                            if (editName.isNotBlank() && editName != character.name) {
                                viewModel.renameCharacter(character.id, editName, seriesId)
                            }
                            isEditing = false
                        },
                        onEscape = {
                            editName = character.name
                            isEditing = false
                        },
                    ),
                textStyle = MaterialTheme.typography.bodySmall,
            )
        } else {
            Column(modifier = Modifier.weight(1f)) {
                Text(character.name, style = MaterialTheme.typography.bodySmall)
                Text(
                    "${item.artworkCount} artworks",
                    style = MaterialTheme.typography.labelSmall,
                    color = OnSurfaceMuted,
                )
            }
        }

        if (!isEditing) {
            IconButton(onClick = { isEditing = true }, modifier = Modifier.size(32.dp)) {
                Icon(Icons.Default.Edit, contentDescription = "Rename", modifier = Modifier.size(16.dp))
            }
            IconButton(
                onClick = { viewModel.requestDeleteCharacter(character, item.artworkCount) },
                modifier = Modifier.size(32.dp),
            ) {
                Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(16.dp))
            }
        } else {
            IconButton(
                onClick = {
                    if (editName.isNotBlank() && editName != character.name) {
                        viewModel.renameCharacter(character.id, editName, seriesId)
                    }
                    isEditing = false
                },
                modifier = Modifier.size(32.dp),
            ) {
                Icon(Icons.Default.Check, contentDescription = "Save", modifier = Modifier.size(16.dp), tint = MaterialTheme.colorScheme.primary)
            }
            IconButton(
                onClick = { editName = character.name; isEditing = false },
                modifier = Modifier.size(32.dp),
            ) {
                Icon(Icons.Default.Close, contentDescription = "Cancel", modifier = Modifier.size(16.dp))
            }
        }
    }
}

// ── Artists tab ───────────────────────────────────────────────────────────────

@Composable
private fun ArtistsTab(
    artists: List<ArtistDto>,
    search: String,
    viewModel: KnowledgeGraphViewModel,
) {
    var searchQuery by remember { mutableStateOf(search) }
    LaunchedEffect(searchQuery) {
        delay(300)
        viewModel.updateArtistSearch(searchQuery)
    }

    val filtered = remember(artists, searchQuery) {
        if (searchQuery.isBlank()) artists
        else artists.filter { it.name.contains(searchQuery, ignoreCase = true) }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = searchQuery,
            onValueChange = { searchQuery = it },
            placeholder = { Text("Search artists…") },
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            singleLine = true,
            trailingIcon = {
                if (searchQuery.isNotEmpty()) {
                    IconButton(onClick = { searchQuery = "" }) {
                        Icon(Icons.Default.Close, contentDescription = "Clear")
                    }
                }
            },
        )
        Text(
            "${filtered.size} artists",
            style = MaterialTheme.typography.labelSmall,
            color = OnSurfaceMuted,
            modifier = Modifier.padding(horizontal = 16.dp).padding(bottom = 8.dp),
        )
        LazyColumn(modifier = Modifier.fillMaxSize()) {
            items(filtered, key = { it.id }) { artist ->
                ArtistRow(artist = artist, viewModel = viewModel)
                HorizontalDivider(color = Surface700)
            }
        }
    }
}

@Composable
private fun ArtistRow(
    artist: ArtistDto,
    viewModel: KnowledgeGraphViewModel,
) {
    var isEditing by remember(artist.id) { mutableStateOf(false) }
    var editName by remember(artist.name) { mutableStateOf(artist.name) }
    val focusRequester = remember { FocusRequester() }

    LaunchedEffect(isEditing) {
        if (isEditing) runCatching { focusRequester.requestFocus() }
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (isEditing) {
            OutlinedTextField(
                value = editName,
                onValueChange = { editName = it },
                singleLine = true,
                modifier = Modifier
                    .weight(1f)
                    .focusRequester(focusRequester)
                    .onEnterOrEscape(
                        onEnter = {
                            if (editName.isNotBlank() && editName != artist.name) {
                                viewModel.renameArtist(artist.id, editName)
                            }
                            isEditing = false
                        },
                        onEscape = {
                            editName = artist.name
                            isEditing = false
                        },
                    ),
                textStyle = MaterialTheme.typography.bodyMedium,
            )
        } else {
            Column(modifier = Modifier.weight(1f)) {
                Text(artist.name, style = MaterialTheme.typography.bodyMedium)
                Text(
                    "${artist.artworkCount} artworks",
                    style = MaterialTheme.typography.labelSmall,
                    color = OnSurfaceMuted,
                )
            }
        }

        if (!isEditing) {
            IconButton(onClick = { isEditing = true }, modifier = Modifier.size(36.dp)) {
                Icon(Icons.Default.Edit, contentDescription = "Rename", modifier = Modifier.size(18.dp))
            }
            IconButton(
                onClick = { viewModel.requestDeleteArtist(artist) },
                modifier = Modifier.size(36.dp),
            ) {
                Icon(
                    Icons.Default.Delete,
                    contentDescription = "Delete",
                    tint = MaterialTheme.colorScheme.error,
                    modifier = Modifier.size(18.dp),
                )
            }
        } else {
            IconButton(
                onClick = {
                    if (editName.isNotBlank() && editName != artist.name) {
                        viewModel.renameArtist(artist.id, editName)
                    }
                    isEditing = false
                },
                modifier = Modifier.size(36.dp),
            ) {
                Icon(Icons.Default.Check, contentDescription = "Save", modifier = Modifier.size(18.dp), tint = MaterialTheme.colorScheme.primary)
            }
            IconButton(
                onClick = { editName = artist.name; isEditing = false },
                modifier = Modifier.size(36.dp),
            ) {
                Icon(Icons.Default.Close, contentDescription = "Cancel", modifier = Modifier.size(18.dp))
            }
        }
    }
}