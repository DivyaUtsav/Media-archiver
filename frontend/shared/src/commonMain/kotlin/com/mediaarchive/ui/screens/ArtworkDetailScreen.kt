package com.mediaarchive.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.mediaarchive.data.AppContainer
import com.mediaarchive.data.api.*
import com.mediaarchive.ui.components.*
import com.mediaarchive.ui.theme.OnSurfaceMuted
import com.mediaarchive.ui.theme.Surface700
import com.mediaarchive.viewmodel.ArtworkDetailViewModel
import com.mediaarchive.viewmodel.TagEditState
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.draw.clip

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ArtworkDetailScreen(
    viewModel: ArtworkDetailViewModel,
    galleryViewModel: com.mediaarchive.viewmodel.GalleryViewModel,
    onBack: () -> Unit,
    onNavigate: (Int) -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val galleryState by galleryViewModel.state.collectAsState()

    val currentIndex = galleryState.artworks.indexOfFirst { it.id == state.artwork?.id }
    val prevId = if (currentIndex > 0) galleryState.artworks[currentIndex - 1].id else null
    val nextId = if (currentIndex != -1 && currentIndex < galleryState.artworks.size - 1) galleryState.artworks[currentIndex + 1].id else null

    LaunchedEffect(currentIndex, galleryState.artworks.size) {
        if (currentIndex != -1 && currentIndex >= galleryState.artworks.size - 4) {
            galleryViewModel.loadMore()
        }
    }

    var dragOffset by remember { mutableStateOf(0f) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Artwork Detail") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    if (!state.isEditing) {
                        IconButton(onClick = viewModel::startEditing) {
                            Icon(Icons.Default.Edit, contentDescription = "Edit tags")
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
    ) { padding ->
        Box(modifier = Modifier
            .padding(padding)
            .fillMaxSize()
            .pointerInput(prevId, nextId) {
                detectHorizontalDragGestures(
                    onDragStart = { dragOffset = 0f },
                    onDragEnd = {
                        if (dragOffset > 50 && prevId != null) onNavigate(prevId)
                        else if (dragOffset < -50 && nextId != null) onNavigate(nextId)
                    },
                    onHorizontalDrag = { change, dragAmount ->
                        dragOffset += dragAmount
                    }
                )
            }
        ) {
            when {
                state.isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                state.error != null -> {
                    Column(modifier = Modifier.align(Alignment.Center), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Failed to load artwork")
                        Button(onClick = viewModel::load) { Text("Retry") }
                    }
                }
                state.artwork != null -> {
                    val artwork = state.artwork!!
                    Column(
                        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                    ) {
                        // Hero image box with navigation arrows
                        Box(modifier = Modifier.fillMaxWidth().heightIn(max = 600.dp)) {
                            AsyncImage(
                                model = AppContainer.apiClient.mediaUrl(artwork.id),
                                contentDescription = "Artwork",
                                contentScale = ContentScale.Fit,
                                modifier = Modifier.fillMaxSize(),
                            )
                            
                            if (prevId != null) {
                                IconButton(
                                    onClick = { onNavigate(prevId) },
                                    modifier = Modifier
                                        .align(Alignment.CenterStart)
                                        .padding(8.dp)
                                        .clip(CircleShape)
                                        .background(Color.Black.copy(alpha = 0.5f))
                                ) {
                                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, contentDescription = "Previous", tint = Color.White)
                                }
                            }

                            if (nextId != null) {
                                IconButton(
                                    onClick = { onNavigate(nextId) },
                                    modifier = Modifier
                                        .align(Alignment.CenterEnd)
                                        .padding(8.dp)
                                        .clip(CircleShape)
                                        .background(Color.Black.copy(alpha = 0.5f))
                                ) {
                                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = "Next", tint = Color.White)
                                }
                            }
                        }

                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(16.dp),
                        ) {
                            if (state.isEditing && state.editState != null) {
                                EditPanel(
                                    editState = state.editState!!,
                                    api = AppContainer.apiClient,
                                    onUpdate = viewModel::updateEditState,
                                    onSave = viewModel::saveTags,
                                    onCancel = viewModel::cancelEditing,
                                    isSaving = state.isSaving,
                                    saveError = state.saveError,
                                    onCreateCharacter = viewModel::createAndAddCharacter,
                                    onCreateArtist = viewModel::createAndAddArtist,
                                )
                            } else {
                                ReadOnlyTagPanel(artwork)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ReadOnlyTagPanel(artwork: ArtworkDetailDto) {
    // Rating + art type row
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        artwork.contentRating?.let { RatingBadge(it) }
        artwork.artType?.let { ArtTypeBadge(it) }
    }

    // Characters
    if (artwork.characters.isNotEmpty()) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Characters", style = MaterialTheme.typography.labelMedium, color = OnSurfaceMuted)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                artwork.characters.forEach { c ->
                    if (c.isManual) TagChip("${c.name} · ${c.series.name}")
                    else ConfidenceChip("${c.name} · ${c.series.name}", c.confidence)
                }
            }
        }
    }

    // Artists
    if (artwork.artists.isNotEmpty()) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("Artists", style = MaterialTheme.typography.labelMedium, color = OnSurfaceMuted)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                artwork.artists.forEach { a ->
                    if (a.isManual) TagChip(a.name)
                    else ConfidenceChip(a.name, a.confidence)
                }
            }
        }
    }

    // Source info
    HorizontalDivider(color = Surface700)
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Source", style = MaterialTheme.typography.labelMedium, color = OnSurfaceMuted)
        artwork.platformContext?.let {
            if (it.subreddit != null) Text("r/${it.subreddit}", style = MaterialTheme.typography.bodySmall)
            if (it.title != null) Text(it.title, style = MaterialTheme.typography.bodySmall)
        }
        artwork.publicationPlatform?.let {
            Text("Published on: ${it.name}", style = MaterialTheme.typography.bodySmall, color = OnSurfaceMuted)
        }
    }
}

@Composable
private fun EditPanel(
    editState: TagEditState,
    api: com.mediaarchive.data.api.ApiClient,
    onUpdate: (TagEditState) -> Unit,
    onSave: () -> Unit,
    onCancel: () -> Unit,
    isSaving: Boolean,
    saveError: String?,
    onCreateCharacter: (String, Int) -> Unit,
    onCreateArtist: (String) -> Unit,
) {
    var characterQuery by remember { mutableStateOf("") }
    var characterResults by remember { mutableStateOf<List<CharacterTagDto>>(emptyList()) }
    var artistQuery by remember { mutableStateOf("") }
    var artistResults by remember { mutableStateOf<List<ArtistTagDto>>(emptyList()) }
    var showCreateCharacterDialog by remember { mutableStateOf(false) }
    var showCreateArtistDialog by remember { mutableStateOf(false) }
    var pendingCreateName by remember { mutableStateOf("") }

    LaunchedEffect(characterQuery) {
        if (characterQuery.length >= 2) {
            runCatching { api.searchCharacters(characterQuery) }.onSuccess {
                characterResults = it.items.map { c ->
                    CharacterTagDto(id = c.id, name = c.name, series = c.series ?: SeriesDto(0, "Unknown"), confidence = null, isManual = true)
                }
            }
        } else characterResults = emptyList()
    }

    LaunchedEffect(artistQuery) {
        if (artistQuery.length >= 2) {
            runCatching { api.searchArtists(artistQuery) }.onSuccess {
                artistResults = it.items.map { a -> ArtistTagDto(id = a.id, name = a.name, confidence = null, isManual = true) }
            }
        } else artistResults = emptyList()
    }

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("Edit Tags", style = MaterialTheme.typography.titleMedium)

        // Content rating
        Text("Content Rating", style = MaterialTheme.typography.labelMedium, color = OnSurfaceMuted)
        com.mediaarchive.ui.components.RatingSelector(selected = editState.contentRating, onSelected = { onUpdate(editState.copy(contentRating = it)) })

        // Art type
        Text("Art Type", style = MaterialTheme.typography.labelMedium, color = OnSurfaceMuted)
        com.mediaarchive.ui.components.ArtTypeSelector(selected = editState.artType, onSelected = { onUpdate(editState.copy(artType = it)) })

        // Characters
        Text("Characters", style = MaterialTheme.typography.labelMedium, color = OnSurfaceMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            editState.characters.forEach { c ->
                TagChip("${c.name} · ${c.series.name}", onRemove = { onUpdate(editState.copy(characters = editState.characters.filter { it.id != c.id })) })
            }
        }
        SearchableDropdown(
            label = "Add character…",
            query = characterQuery,
            onQueryChange = { characterQuery = it },
            results = characterResults,
            onSelect = { c -> onUpdate(editState.copy(characters = editState.characters + c)); characterQuery = "" },
            itemLabel = { "${it.name} · ${it.series.name}" },
            onCreateNew = { name -> pendingCreateName = name; showCreateCharacterDialog = true },
        )

        // Artists
        Text("Artists", style = MaterialTheme.typography.labelMedium, color = OnSurfaceMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            editState.artists.forEach { a ->
                TagChip(a.name, onRemove = { onUpdate(editState.copy(artists = editState.artists.filter { it.id != a.id })) })
            }
        }
        SearchableDropdown(
            label = "Add artist…",
            query = artistQuery,
            onQueryChange = { artistQuery = it },
            results = artistResults,
            onSelect = { a -> onUpdate(editState.copy(artists = editState.artists + a)); artistQuery = "" },
            itemLabel = { it.name },
            onCreateNew = { name -> pendingCreateName = name; showCreateArtistDialog = true },
        )

        // Publication platform
        Text("Publication Platform", style = MaterialTheme.typography.labelMedium, color = OnSurfaceMuted)
        SourcePlatformSelector(
            selected = editState.publicationPlatform,
            api = api,
            onSelected = { onUpdate(editState.copy(publicationPlatform = it)) },
        )

        saveError?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(onClick = onCancel, enabled = !isSaving) { Text("Cancel") }
            Button(onClick = onSave, enabled = !isSaving) {
                if (isSaving) CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                else Text("Save")
            }
        }
    }

    if (showCreateCharacterDialog) {
        CreateCharacterDialog(
            initialName = pendingCreateName,
            api = api,
            onCreate = { name, seriesId ->
                onCreateCharacter(name, seriesId)
                showCreateCharacterDialog = false
            },
            onDismiss = { showCreateCharacterDialog = false },
        )
    }

    if (showCreateArtistDialog) {
        AlertDialog(
            onDismissRequest = { showCreateArtistDialog = false },
            title = { Text("Create Artist") },
            text = { Text("Create artist \"$pendingCreateName\"?") },
            confirmButton = {
                Button(onClick = {
                    onCreateArtist(pendingCreateName)
                    showCreateArtistDialog = false
                }) { Text("Create") }
            },
            dismissButton = { OutlinedButton(onClick = { showCreateArtistDialog = false }) { Text("Cancel") } },
        )
    }
}
