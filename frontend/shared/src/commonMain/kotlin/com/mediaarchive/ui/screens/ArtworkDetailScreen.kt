package com.mediaarchive.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
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
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import kotlinx.coroutines.launch
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
fun ArtworkDetailScreen(
    initialArtworkId: Int,
    galleryViewModel: com.mediaarchive.viewmodel.GalleryViewModel,
    onBack: () -> Unit,
    onArtistClick: (Int) -> Unit,
) {
    val galleryState by galleryViewModel.state.collectAsState()
    val initialIndex = remember { galleryState.artworks.indexOfFirst { it.id == initialArtworkId }.coerceAtLeast(0) }
    val pagerState = androidx.compose.foundation.pager.rememberPagerState(initialPage = initialIndex) { galleryState.artworks.size }

    LaunchedEffect(pagerState.currentPage, galleryState.artworks.size) {
        if (pagerState.currentPage >= galleryState.artworks.size - 4) {
            galleryViewModel.loadMore()
        }
    }

    androidx.compose.foundation.pager.HorizontalPager(
        state = pagerState,
        modifier = Modifier.fillMaxSize(),
        beyondViewportPageCount = 1,
    ) { page ->
        val artwork = galleryState.artworks[page]
        val vm = remember(artwork.id) { ArtworkDetailViewModel(AppContainer.apiClient, artwork.id) }
        
        ArtworkDetailPage(
            viewModel = vm,
            onBack = onBack,
            onDelete = { galleryViewModel.removeArtwork(artwork.id) },
            onArtistClick = onArtistClick,
        )
    }

    if (com.mediaarchive.isDesktop) {
        val scope = rememberCoroutineScope()
        Box(modifier = Modifier.fillMaxSize()) {
            if (pagerState.currentPage > 0) {
                IconButton(
                    onClick = { scope.launch { pagerState.animateScrollToPage(pagerState.currentPage - 1) } },
                    modifier = Modifier.align(Alignment.CenterStart).padding(16.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.5f))
                ) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, contentDescription = "Previous", tint = Color.White)
                }
            }
            if (pagerState.currentPage < galleryState.artworks.size - 1) {
                IconButton(
                    onClick = { scope.launch { pagerState.animateScrollToPage(pagerState.currentPage + 1) } },
                    modifier = Modifier.align(Alignment.CenterEnd).padding(16.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.5f))
                ) {
                    Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = "Next", tint = Color.White)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ArtworkDetailPage(
    viewModel: ArtworkDetailViewModel,
    onBack: () -> Unit,
    onDelete: () -> Unit,
    onArtistClick: (Int) -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val scaffoldState = rememberBottomSheetScaffoldState()
    var isImmersive by remember { mutableStateOf(false) }

    BottomSheetScaffold(
        scaffoldState = scaffoldState,
        sheetPeekHeight = 100.dp,
        sheetContent = {
            Column(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp).padding(bottom = 16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                if (state.isLoading) {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.CenterHorizontally))
                } else if (state.error != null) {
                    Text("Failed to load artwork")
                } else if (state.artwork != null) {
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
                        ReadOnlyTagPanel(state.artwork!!, onArtistClick)
                    }
                }
            }
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().background(Color.Black)) {
            when {
                state.artwork != null -> {
                    AsyncImage(
                        model = AppContainer.apiClient.mediaUrl(state.artwork!!.id),
                        contentDescription = "Artwork",
                        contentScale = ContentScale.Fit,
                        modifier = Modifier.fillMaxSize().clickable(
                            interactionSource = remember { MutableInteractionSource() },
                            indication = null
                        ) { isImmersive = !isImmersive }
                    )
                }
            }

            androidx.compose.animation.AnimatedVisibility(
                visible = !isImmersive,
                enter = androidx.compose.animation.fadeIn(),
                exit = androidx.compose.animation.fadeOut()
            ) {
                TopAppBar(
                    title = { },
                    navigationIcon = {
                        IconButton(onClick = onBack) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                    },
                    actions = {
                        if (!state.isEditing) {
                            var showDeleteConfirm by remember { mutableStateOf(false) }
                            IconButton(onClick = { showDeleteConfirm = true }) {
                                Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error)
                            }
                            IconButton(onClick = viewModel::startEditing) {
                                Icon(Icons.Default.Edit, contentDescription = "Edit tags")
                            }
                            if (showDeleteConfirm) {
                                AlertDialog(
                                    onDismissRequest = { showDeleteConfirm = false },
                                    title = { Text("Delete Artwork") },
                                    text = { Text("Are you sure you want to delete this artwork? The file will be permanently removed.") },
                                    confirmButton = {
                                        Button(onClick = {
                                            viewModel.deleteArtwork { onDelete() }
                                            showDeleteConfirm = false
                                        }, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)) {
                                            Text("Delete")
                                        }
                                    },
                                    dismissButton = {
                                        OutlinedButton(onClick = { showDeleteConfirm = false }) { Text("Cancel") }
                                    }
                                )
                            }
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = Color.Black.copy(alpha = 0.5f),
                        navigationIconContentColor = Color.White,
                        actionIconContentColor = Color.White
                    ),
                )
            }
        }
    }
}

@Composable
private fun ReadOnlyTagPanel(artwork: ArtworkDetailDto, onArtistClick: (Int) -> Unit) {
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
                    if (a.isManual) TagChip(a.name, onClick = { onArtistClick(a.id) })
                    else ConfidenceChip(a.name, a.confidence, onClick = { onArtistClick(a.id) })
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
