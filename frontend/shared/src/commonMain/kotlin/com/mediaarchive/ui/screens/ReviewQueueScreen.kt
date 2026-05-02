package com.mediaarchive.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
import com.mediaarchive.ui.theme.RatingNSFW
import com.mediaarchive.viewmodel.ReviewQueueViewModel
import com.mediaarchive.viewmodel.ReviewTagEditState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewQueueScreen(
    viewModel: ReviewQueueViewModel,
    onBack: () -> Unit,
) {
    val state by viewModel.state.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Review Queue · ${state.queueCount} pending") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
    ) { padding ->
        Box(modifier = Modifier.padding(padding).fillMaxSize()) {
            when {
                state.isLoading -> CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                state.isEmpty -> {
                    Column(
                        modifier = Modifier.align(Alignment.Center),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text("✓", style = MaterialTheme.typography.displayLarge, color = MaterialTheme.colorScheme.primary)
                        Text("Queue is empty", style = MaterialTheme.typography.titleMedium)
                        Text("All artworks are tagged.", style = MaterialTheme.typography.bodyMedium, color = OnSurfaceMuted)
                        Button(onClick = onBack) { Text("Back to Gallery") }
                    }
                }
                state.error != null -> {
                    Column(modifier = Modifier.align(Alignment.Center), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Error: ${state.error}")
                        Button(onClick = viewModel::loadNext) { Text("Retry") }
                    }
                }
                state.currentArtwork != null -> {
                    ReviewArtworkPanel(
                        artwork = state.currentArtwork!!,
                        editState = state.tagEditState,
                        pendingCategories = state.pendingCategories,
                        api = AppContainer.apiClient,
                        onUpdateEditState = viewModel::updateEditState,
                        onCreateCharacter = viewModel::createAndAddCharacter,
                        onCreateArtist = viewModel::createAndAddArtist,
                        onSubmit = viewModel::submit,
                        isSubmitting = state.isSubmitting,
                        submitError = state.submitError,
                    )
                }
            }
        }
    }
}

@Composable
private fun ReviewArtworkPanel(
    artwork: QueueArtworkDto,
    editState: ReviewTagEditState,
    pendingCategories: List<String>,
    api: ApiClient,
    onUpdateEditState: (ReviewTagEditState) -> Unit,
    onCreateCharacter: (String, Int) -> Unit,
    onCreateArtist: (String) -> Unit,
    onSubmit: () -> Unit,
    isSubmitting: Boolean,
    submitError: String?,
) {
    var characterQuery by remember { mutableStateOf("") }
    var characterResults by remember { mutableStateOf<List<CharacterDto>>(emptyList()) }
    var artistQuery by remember { mutableStateOf("") }
    var artistResults by remember { mutableStateOf<List<ArtistDto>>(emptyList()) }
    var showCreateCharacterDialog by remember { mutableStateOf(false) }
    var showCreateArtistDialog by remember { mutableStateOf(false) }
    var pendingCreateName by remember { mutableStateOf("") }

    LaunchedEffect(characterQuery) {
        if (characterQuery.length >= 2)
            runCatching { api.searchCharacters(characterQuery) }.onSuccess { characterResults = it.items }
        else characterResults = emptyList()
    }
    LaunchedEffect(artistQuery) {
        if (artistQuery.length >= 2)
            runCatching { api.searchArtists(artistQuery) }.onSuccess { artistResults = it.items }
        else artistResults = emptyList()
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
    ) {
        // Image
        AsyncImage(
            model = AppContainer.apiClient.mediaUrl(artwork.id),
            contentDescription = "Pending artwork",
            contentScale = ContentScale.FillWidth,
            modifier = Modifier.fillMaxWidth().heightIn(max = 500.dp),
        )

        // Platform context
        artwork.platformContext?.let { ctx ->
            Surface(tonalElevation = 1.dp, modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(12.dp)) {
                    if (ctx.subreddit != null) Text("r/${ctx.subreddit}", style = MaterialTheme.typography.labelMedium)
                    if (ctx.title != null) Text(ctx.title, style = MaterialTheme.typography.bodySmall, color = OnSurfaceMuted)
                    if (ctx.flair != null) Text(ctx.flair, style = MaterialTheme.typography.labelSmall, color = OnSurfaceMuted)
                }
            }
        }

        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {

            // ── Content rating ──────────────────────────────────────────────
            if ("content_rating" in pendingCategories) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    SectionHeader("Content Rating", editState.contentRatingSuggestion?.let { "Suggested: $it" })
                    RatingSelector(selected = editState.contentRating, onSelected = { onUpdateEditState(editState.copy(contentRating = it)) })
                }
            }

            // ── Art type ─────────────────────────────────────────────────────
            if ("art_type" in pendingCategories) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    SectionHeader("Art Type", editState.artTypeSuggestion?.let { "Suggested: $it" })
                    ArtTypeSelector(selected = editState.artType, onSelected = { onUpdateEditState(editState.copy(artType = it)) })
                }
            }

            // ── Characters ───────────────────────────────────────────────────
            if ("character" in pendingCategories) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    SectionHeader("Characters", null)
                    if (editState.characterSuggestions.isNotEmpty()) {
                        Text("Suggestions:", style = MaterialTheme.typography.labelSmall, color = OnSurfaceMuted)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            editState.characterSuggestions.forEach { s ->
                                SuggestionChip(
                                    onClick = {
                                        if (s.characterId != null) {
                                            val char = CharacterDto(s.characterId, s.name)
                                            onUpdateEditState(editState.copy(characters = editState.characters + char))
                                        }
                                    },
                                    label = { Text("${s.name} (${(s.confidence * 100).toInt()}%)") },
                                )
                            }
                        }
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        editState.characters.forEach { c ->
                            TagChip(c.name, onRemove = { onUpdateEditState(editState.copy(characters = editState.characters.filter { it.id != c.id })) })
                        }
                    }
                    SearchableDropdown(
                        label = "Search character…",
                        query = characterQuery,
                        onQueryChange = { characterQuery = it },
                        results = characterResults,
                        onSelect = { c -> onUpdateEditState(editState.copy(characters = editState.characters + c)); characterQuery = "" },
                        itemLabel = { "${it.name}" + if (it.series != null) " · ${it.series!!.name}" else "" },
                        onCreateNew = { name -> pendingCreateName = name; showCreateCharacterDialog = true },
                    )
                }
            }

            // ── Artists ──────────────────────────────────────────────────────
            if ("artist" in pendingCategories) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    SectionHeader("Artists", null)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        editState.artists.forEach { a ->
                            TagChip(a.name, onRemove = { onUpdateEditState(editState.copy(artists = editState.artists.filter { it.id != a.id })) })
                        }
                    }
                    SearchableDropdown(
                        label = "Search artist…",
                        query = artistQuery,
                        onQueryChange = { artistQuery = it },
                        results = artistResults,
                        onSelect = { a -> onUpdateEditState(editState.copy(artists = editState.artists + a)); artistQuery = "" },
                        itemLabel = { it.name },
                        onCreateNew = { name -> pendingCreateName = name; showCreateArtistDialog = true },
                    )
                }
            }

            submitError?.let { Text("Error: $it", color = RatingNSFW, style = MaterialTheme.typography.bodySmall) }

            Button(
                onClick = onSubmit,
                enabled = !isSubmitting,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (isSubmitting) CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                else Text("Confirm & Next")
            }
        }
    }

    // Create character dialog
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

    // Create artist dialog
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

@Composable
private fun SectionHeader(title: String, hint: String?) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.titleSmall)
        hint?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = OnSurfaceMuted) }
    }
}

@Composable
private fun CreateCharacterDialog(
    initialName: String,
    api: ApiClient,
    onCreate: (String, Int) -> Unit,
    onDismiss: () -> Unit,
) {
    var name by remember { mutableStateOf(initialName) }
    var seriesQuery by remember { mutableStateOf("") }
    var seriesResults by remember { mutableStateOf<List<SeriesDto>>(emptyList()) }
    var selectedSeries by remember { mutableStateOf<SeriesDto?>(null) }

    LaunchedEffect(seriesQuery) {
        if (seriesQuery.length >= 1)
            runCatching { api.getSeries() }.onSuccess {
                seriesResults = it.items.filter { s -> s.name.contains(seriesQuery, ignoreCase = true) }
            }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Create Character") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Character name") }, singleLine = true)
                selectedSeries?.let { Text("Series: ${it.name}", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary) }
                SearchableDropdown(
                    label = "Search series…",
                    query = seriesQuery,
                    onQueryChange = { seriesQuery = it },
                    results = seriesResults,
                    onSelect = { s -> selectedSeries = s; seriesQuery = s.name },
                    itemLabel = { it.name },
                )
            }
        },
        confirmButton = {
            Button(
                onClick = { selectedSeries?.let { onCreate(name, it.id) } },
                enabled = name.isNotBlank() && selectedSeries != null,
            ) { Text("Create") }
        },
        dismissButton = { OutlinedButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
