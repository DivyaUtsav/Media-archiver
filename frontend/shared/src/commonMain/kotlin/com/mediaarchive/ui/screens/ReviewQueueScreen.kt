package com.mediaarchive.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import coil3.compose.AsyncImage
import com.mediaarchive.data.AppContainer
import com.mediaarchive.data.api.*
import com.mediaarchive.ui.components.*
import com.mediaarchive.ui.theme.OnSurfaceMuted
import com.mediaarchive.ui.theme.RatingNSFW
import com.mediaarchive.viewmodel.ReviewQueueViewModel
import com.mediaarchive.viewmodel.ReviewTagEditState
import kotlinx.coroutines.delay
import androidx.compose.animation.Crossfade
import androidx.compose.foundation.background
import androidx.compose.ui.graphics.Color
import com.mediaarchive.data.PendingCategory
import com.mediaarchive.ui.onEnterKey
import com.mediaarchive.ui.onEscapeKey
import com.mediaarchive.ui.onEnterOrEscape
import androidx.compose.foundation.border
import androidx.compose.foundation.shape.RoundedCornerShape
import com.mediaarchive.ui.theme.AccentTeal
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.KeyEvent
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusTarget
import androidx.compose.ui.input.key.onPreviewKeyEvent

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReviewQueueScreen(
    viewModel: ReviewQueueViewModel,
    onBack: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    var showDeleteConfirm by remember { mutableStateOf(false) }
    var characterQuery by remember { mutableStateOf("") }
    var artistQuery by remember { mutableStateOf("") }
    var characterResults by remember { mutableStateOf<List<CharacterDto>>(emptyList()) }
    var artistResults by remember { mutableStateOf<List<ArtistDto>>(emptyList()) }

    val sections = remember(state.pendingCategories) {
        buildSectionList(state.pendingCategories)
    }
    var kbState by remember(state.currentArtwork?.id) {
        mutableStateOf(ReviewKeyboardState(sections = sections, focusedSectionIndex = 0))
    }
    LaunchedEffect(sections) {
        kbState = kbState.copy(sections = sections, focusedSectionIndex = 0)
    }

    val screenFocusRequester = remember { FocusRequester() }
    LaunchedEffect(Unit) {
        screenFocusRequester.requestFocus()
    }
    // Re-grab focus when search deactivates so keyboard nav works again
    LaunchedEffect(kbState.isSearchActive) {
        if (!kbState.isSearchActive) {
            runCatching { screenFocusRequester.requestFocus() }
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .focusRequester(screenFocusRequester)
            .focusTarget()
            .onPreviewKeyEvent { event ->
                handleReviewKeyEvent(
                    event = event,
                    kbState = kbState,
                    editState = state.tagEditState,
                    characterResults = characterResults,
                    artistResults = artistResults,
                    characterQuery = characterQuery,
                    artistQuery = artistQuery,
                    onKbState = { kbState = it },
                    onUpdateEditState = viewModel::updateEditState,
                    onCharacterQueryChange = { characterQuery = it },
                    onArtistQueryChange = { artistQuery = it },
                    onSubmit = viewModel::submit,
                    onSkip = viewModel::skipCurrent,
                    onBack = onBack,
                    isSubmitting = state.isSubmitting,
                )
            }
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        val label = state.selectedPlatform?.let { "${it.name} (${it.count})" }
                            ?: "All Platforms (${state.totalCount})"
                        Text("Review Queue · $label")
                    },
                    navigationIcon = {
                        IconButton(onClick = onBack) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                    },
                    actions = {
                        if (state.currentArtwork != null) {
                            IconButton(
                                onClick = viewModel::skipCurrent,
                                enabled = !state.isSubmitting,
                            ) {
                                Icon(
                                    Icons.Default.SkipNext,
                                    contentDescription = "Skip",
                                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            IconButton(onClick = { showDeleteConfirm = true }) {
                                Icon(
                                    Icons.Default.Delete,
                                    contentDescription = "Delete",
                                    tint = MaterialTheme.colorScheme.error,
                                )
                            }
                            if (showDeleteConfirm) {
                                AlertDialog(
                                    onDismissRequest = { showDeleteConfirm = false },
                                    modifier = Modifier.onEnterOrEscape(
                                        onEnter = {
                                            viewModel.deleteCurrent()
                                            showDeleteConfirm = false
                                        },
                                        onEscape = { showDeleteConfirm = false },
                                    ),
                                    title = { Text("Delete Artwork") },
                                    text = { Text("Are you sure you want to delete this pending artwork? The file will be permanently removed.") },
                                    confirmButton = {
                                        Button(
                                            onClick = {
                                                viewModel.deleteCurrent()
                                                showDeleteConfirm = false
                                            },
                                            colors = ButtonDefaults.buttonColors(
                                                containerColor = MaterialTheme.colorScheme.error,
                                            ),
                                        ) {
                                            Text("Delete")
                                        }
                                    },
                                    dismissButton = {
                                        OutlinedButton(onClick = { showDeleteConfirm = false }) {
                                            Text("Cancel")
                                        }
                                    },
                                )
                            }
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.surface,
                    ),
                )
            },
        ) { padding ->
            Column(modifier = Modifier.padding(padding).fillMaxSize()) {
                // Platform filter dropdown
                var menuExpanded by remember { mutableStateOf(false) }
                val options = listOf<Pair<String, com.mediaarchive.data.api.QueuePlatformDto?>>(
                    "All Platforms (${state.totalCount})" to null
                ) + state.platforms
                    .sortedWith(
                        compareByDescending<com.mediaarchive.data.api.QueuePlatformDto> { it.count }
                            .thenBy { it.name }
                    )
                    .map { "${it.name} (${it.count})" to it }
                val selectedLabel = options.find { it.second?.id == state.selectedPlatform?.id }?.first
                    ?: options[0].first
                if (state.platforms.size > 1) {
                    ExposedDropdownMenuBox(
                        expanded = menuExpanded,
                        onExpandedChange = { menuExpanded = !menuExpanded },
                        modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
                    ) {
                        OutlinedTextField(
                            value = selectedLabel,
                            onValueChange = {},
                            readOnly = true,
                            label = { Text("Platform Filter") },
                            trailingIcon = {
                                ExposedDropdownMenuDefaults.TrailingIcon(expanded = menuExpanded)
                            },
                            modifier = Modifier
                                .menuAnchor(MenuAnchorType.PrimaryNotEditable)
                                .fillMaxWidth(),
                        )
                        ExposedDropdownMenu(
                            expanded = menuExpanded,
                            onDismissRequest = { menuExpanded = false },
                        ) {
                            options.forEach { (label, platform) ->
                                DropdownMenuItem(
                                    text = { Text(label) },
                                    onClick = {
                                        if (state.selectedPlatform?.id != platform?.id) {
                                            viewModel.selectPlatform(platform)
                                        }
                                        menuExpanded = false
                                    },
                                )
                            }
                        }
                    }
                }

                Box(modifier = Modifier.fillMaxSize()) {
                    when {
                        state.isLoading -> CircularProgressIndicator(
                            modifier = Modifier.align(Alignment.Center),
                        )
                        state.isEmpty -> {
                            Column(
                                modifier = Modifier.align(Alignment.Center),
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Text(
                                    "✓",
                                    style = MaterialTheme.typography.displayLarge,
                                    color = MaterialTheme.colorScheme.primary,
                                )
                                Text("Queue is empty", style = MaterialTheme.typography.titleMedium)
                                Text(
                                    "All artworks are tagged.",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = OnSurfaceMuted,
                                )
                                Button(onClick = onBack) { Text("Back to Gallery") }
                            }
                        }
                        state.error != null -> {
                            Column(
                                modifier = Modifier.align(Alignment.Center),
                                horizontalAlignment = Alignment.CenterHorizontally,
                            ) {
                                Text("Error: ${state.error}")
                                Button(onClick = viewModel::loadNext) { Text("Retry") }
                            }
                        }
                        state.currentArtwork != null -> {
                            Crossfade(
                                targetState = state.currentArtwork,
                                label = "queue_crossfade",
                            ) { artwork ->
                                ReviewArtworkPanel(
                                    artwork = artwork!!,
                                    editState = state.tagEditState,
                                    pendingCategories = state.pendingCategories,
                                    api = AppContainer.apiClient,
                                    onUpdateEditState = viewModel::updateEditState,
                                    onCreateCharacter = viewModel::createAndAddCharacter,
                                    onCreateArtist = viewModel::createAndAddArtist,
                                    onSubmit = viewModel::submit,
                                    onSkip = viewModel::skipCurrent,
                                    isSubmitting = state.isSubmitting,
                                    submitError = state.submitError,
                                    characterQuery = characterQuery,
                                    onCharacterQueryChange = { characterQuery = it },
                                    artistQuery = artistQuery,
                                    onArtistQueryChange = { artistQuery = it },
                                    kbState = kbState,
                                    onCharacterResultsChanged = { characterResults = it },
                                    onArtistResultsChanged = { artistResults = it },
                                )
                            }
                        }
                    }
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
    onSkip: () -> Unit,
    isSubmitting: Boolean,
    submitError: String?,
    // FIX: These are the lifted query/results from ReviewQueueScreen — do NOT redeclare locally
    characterQuery: String,
    onCharacterQueryChange: (String) -> Unit,
    artistQuery: String,
    onArtistQueryChange: (String) -> Unit,
    kbState: ReviewKeyboardState,
    onCharacterResultsChanged: (List<CharacterDto>) -> Unit,
    onArtistResultsChanged: (List<ArtistDto>) -> Unit,
) {
    val uriHandler = LocalUriHandler.current
    // FIX: Removed the local `characterQuery` / `artistQuery` / `characterResults` / `artistResults`
    // declarations that were shadowing the parameters above. The parameters are the source of truth,
    // owned by ReviewQueueScreen so the keyboard handler can read them.
    var characterResults by remember { mutableStateOf<List<CharacterDto>>(emptyList()) }
    var artistResults by remember { mutableStateOf<List<ArtistDto>>(emptyList()) }
    var showCreateCharacterDialog by remember { mutableStateOf(false) }
    var showCreateArtistDialog by remember { mutableStateOf(false) }
    var pendingCreateName by remember { mutableStateOf("") }

    // These now correctly react to the parameter `characterQuery` / `artistQuery`
    LaunchedEffect(characterQuery) {
        if (characterQuery.length >= 2) {
            delay(300)
            runCatching { api.searchCharacters(characterQuery) }.onSuccess {
                characterResults = it.items
                onCharacterResultsChanged(it.items)
            }
        } else {
            characterResults = emptyList()
            onCharacterResultsChanged(emptyList())
        }
    }
    LaunchedEffect(artistQuery) {
        if (artistQuery.length >= 2) {
            delay(300)
            runCatching { api.searchArtists(artistQuery) }.onSuccess {
                artistResults = it.items
                onArtistResultsChanged(it.items)
            }
        } else {
            artistResults = emptyList()
            onArtistResultsChanged(emptyList())
        }
    }

    if (com.mediaarchive.isDesktop) {
        // ── Desktop: image left, tags right ─────────────────────────────────
        Row(modifier = Modifier.fillMaxSize()) {
            // Image panel — fills all remaining space
            Box(
                modifier = Modifier.weight(1f).fillMaxHeight().background(Color.Black),
                contentAlignment = Alignment.Center,
            ) {
                AsyncImage(
                    model = AppContainer.apiClient.mediaUrl(artwork.id),
                    contentDescription = "Artwork",
                    contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxSize(),
                )
                // Source link overlay bottom-start
                artwork.sourcePlatformUrl?.let { url ->
                    Box(modifier = Modifier.align(Alignment.BottomStart).padding(12.dp)) {
                        TextButton(
                            onClick = { uriHandler.openUri(url) },
                            colors = ButtonDefaults.textButtonColors(
                                contentColor = MaterialTheme.colorScheme.primary,
                            ),
                        ) {
                            Text("Open source ↗", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }

            // Tag panel — fixed width, scrollable
            Column(
                modifier = Modifier
                    .width(360.dp)
                    .fillMaxHeight()
                    .background(MaterialTheme.colorScheme.surface)
                    .verticalScroll(rememberScrollState())
                    .padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                // Platform context
                artwork.platformContext?.let { ctx ->
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        if (ctx.subreddit != null) Text(
                            "r/${ctx.subreddit}",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.primary,
                        )
                        if (ctx.title != null) Text(
                            ctx.title,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    HorizontalDivider()
                }

                TagFormContent(
                    editState = editState,
                    pendingCategories = pendingCategories,
                    api = api,
                    characterQuery = characterQuery,
                    onCharacterQueryChange = onCharacterQueryChange,
                    characterResults = characterResults,
                    artistQuery = artistQuery,
                    onArtistQueryChange = onArtistQueryChange,
                    artistResults = artistResults,
                    kbState = kbState,
                    onUpdateEditState = onUpdateEditState,
                    onCreateCharacter = { name -> pendingCreateName = name; showCreateCharacterDialog = true },
                    onCreateArtist = { name -> pendingCreateName = name; showCreateArtistDialog = true },
                    onSubmit = onSubmit,
                    onSkip = onSkip,
                    isSubmitting = isSubmitting,
                    submitError = submitError,
                )
            }
        }
    } else {
        // ── Mobile: image top, tags below ───────────────────────────────────
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(horizontal = 16.dp)
                .padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Image
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 320.dp)
                    .background(Color.Black),
                contentAlignment = Alignment.Center,
            ) {
                AsyncImage(
                    model = AppContainer.apiClient.mediaUrl(artwork.id),
                    contentDescription = "Artwork",
                    contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            // Platform context
            artwork.platformContext?.let { ctx ->
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    if (ctx.subreddit != null) Text(
                        "r/${ctx.subreddit}",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    if (ctx.title != null) Text(
                        ctx.title,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            artwork.sourcePlatformUrl?.let { url ->
                TextButton(onClick = { uriHandler.openUri(url) }) {
                    Text("Open source ↗", style = MaterialTheme.typography.labelSmall)
                }
            }

            // FIX: Use the passed-in callbacks, not local lambdas writing to deleted locals
            TagFormContent(
                editState = editState,
                pendingCategories = pendingCategories,
                api = api,
                characterQuery = characterQuery,
                onCharacterQueryChange = onCharacterQueryChange,
                characterResults = characterResults,
                artistQuery = artistQuery,
                onArtistQueryChange = onArtistQueryChange,
                artistResults = artistResults,
                onUpdateEditState = onUpdateEditState,
                onCreateCharacter = { name -> pendingCreateName = name; showCreateCharacterDialog = true },
                onCreateArtist = { name -> pendingCreateName = name; showCreateArtistDialog = true },
                onSubmit = onSubmit,
                onSkip = onSkip,
                isSubmitting = isSubmitting,
                submitError = submitError,
            )
        }
    }

    // Dialogs — shared between both layouts
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
            modifier = Modifier.onEnterOrEscape(
                onEnter = { onCreateArtist(pendingCreateName); showCreateArtistDialog = false },
                onEscape = { showCreateArtistDialog = false },
            ),
            title = { Text("Create Artist") },
            text = { Text("Create artist \"$pendingCreateName\"?") },
            confirmButton = {
                Button(onClick = {
                    onCreateArtist(pendingCreateName)
                    showCreateArtistDialog = false
                }) { Text("Create") }
            },
            dismissButton = {
                OutlinedButton(onClick = { showCreateArtistDialog = false }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun SectionHeader(title: String, hint: String?) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(title, style = MaterialTheme.typography.titleSmall)
        hint?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = OnSurfaceMuted) }
    }
}

@Composable
private fun TagFormContent(
    editState: ReviewTagEditState,
    pendingCategories: List<String>,
    api: ApiClient,
    characterQuery: String,
    onCharacterQueryChange: (String) -> Unit,
    characterResults: List<CharacterDto>,
    artistQuery: String,
    onArtistQueryChange: (String) -> Unit,
    artistResults: List<ArtistDto>,
    onUpdateEditState: (ReviewTagEditState) -> Unit,
    onCreateCharacter: (String) -> Unit,
    onCreateArtist: (String) -> Unit,
    onSubmit: () -> Unit,
    onSkip: () -> Unit,
    isSubmitting: Boolean,
    submitError: String?,
    kbState: ReviewKeyboardState = ReviewKeyboardState(),
) {
    val characterFocusRequester = remember { FocusRequester() }
    val artistFocusRequester = remember { FocusRequester() }

    LaunchedEffect(kbState.isSearchActive, kbState.focusedSection) {
        if (kbState.isSearchActive) {
            when (kbState.focusedSection) {
                ReviewSection.CHARACTER -> runCatching { characterFocusRequester.requestFocus() }
                ReviewSection.ARTIST -> runCatching { artistFocusRequester.requestFocus() }
                else -> {}
            }
        }
    }

    @Composable
    fun Modifier.sectionHighlight(section: ReviewSection, kbState: ReviewKeyboardState): Modifier {
        return if (kbState.focusedSection == section) {
            this
                .border(width = 1.5.dp, color = AccentTeal, shape = RoundedCornerShape(8.dp))
                .padding(10.dp)
        } else {
            this.padding(10.dp)
        }
    }

    // ── Content rating ────────────────────────────────────────────────────
    if (PendingCategory.CONTENT_RATING in pendingCategories) {
        Column(
            modifier = Modifier.fillMaxWidth().sectionHighlight(ReviewSection.CONTENT_RATING, kbState),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            SectionHeader(
                "Content Rating",
                editState.contentRatingSuggestion?.let { "Suggested: $it" },
            )
            RatingSelector(
                selected = editState.contentRating,
                onSelected = { onUpdateEditState(editState.copy(contentRating = it)) },
            )
            if (kbState.focusedSection == ReviewSection.CONTENT_RATING) {
                Text(
                    "← → to cycle · Enter to confirm",
                    style = MaterialTheme.typography.labelSmall,
                    color = OnSurfaceMuted,
                )
            }
        }
    }

    // ── Art type ──────────────────────────────────────────────────────────
    if (PendingCategory.ART_TYPE in pendingCategories) {
        Column(
            modifier = Modifier.fillMaxWidth().sectionHighlight(ReviewSection.ART_TYPE, kbState),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            SectionHeader(
                "Art Type",
                editState.artTypeSuggestion?.let { "Suggested: $it" },
            )
            ArtTypeSelector(
                selected = editState.artType,
                onSelected = { onUpdateEditState(editState.copy(artType = it)) },
            )
            if (kbState.focusedSection == ReviewSection.ART_TYPE) {
                Text(
                    "← → to cycle · Enter to confirm",
                    style = MaterialTheme.typography.labelSmall,
                    color = OnSurfaceMuted,
                )
            }
        }
    }

    // ── Characters ────────────────────────────────────────────────────────
    if (PendingCategory.CHARACTER in pendingCategories) {
        Column(
            modifier = Modifier.fillMaxWidth().sectionHighlight(ReviewSection.CHARACTER, kbState),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SectionHeader("Characters", null)
            if (editState.characterSuggestions.isNotEmpty()) {
                Text(
                    "Suggestions:",
                    style = MaterialTheme.typography.labelSmall,
                    color = OnSurfaceMuted,
                )
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    editState.characterSuggestions.forEachIndexed { index, s ->
                        val isHighlighted = kbState.focusedSection == ReviewSection.CHARACTER &&
                                kbState.highlightedSuggestionIndex == index
                        SuggestionChip(
                            onClick = {
                                if (s.characterId != null) {
                                    val char = CharacterDto(s.characterId, s.name ?: "")
                                    onUpdateEditState(editState.copy(characters = editState.characters + char))
                                } else {
                                    onCharacterQueryChange(s.name ?: "")
                                }
                            },
                            label = { Text("${s.name ?: ""} (${(s.confidence * 100).toInt()}%)") },
                            border = if (isHighlighted) FilterChipDefaults.filterChipBorder(
                                enabled = true,
                                selected = true,
                                borderColor = AccentTeal,
                                selectedBorderColor = AccentTeal,
                                borderWidth = 1.5.dp,
                                selectedBorderWidth = 1.5.dp,
                            ) else FilterChipDefaults.filterChipBorder(enabled = true, selected = false),
                        )
                    }
                }
            }
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                editState.characters.forEach { c ->
                    TagChip(
                        c.name,
                        onRemove = {
                            onUpdateEditState(
                                editState.copy(characters = editState.characters.filter { it.id != c.id })
                            )
                        },
                    )
                }
            }
            SearchableDropdown(
                label = "Search character…",
                query = characterQuery,
                onQueryChange = onCharacterQueryChange,
                results = characterResults,
                onSelect = { c ->
                    onUpdateEditState(editState.copy(characters = editState.characters + c))
                    onCharacterQueryChange("")
                },
                itemLabel = { it.name + if (it.series != null) " · ${it.series!!.name}" else "" },
                onCreateNew = onCreateCharacter,
                highlightedIndex = if (kbState.focusedSection == ReviewSection.CHARACTER && kbState.isSearchActive)
                    kbState.highlightedResultIndex else -1,
                focusRequester = characterFocusRequester,
            )
            if (kbState.focusedSection == ReviewSection.CHARACTER && !kbState.isSearchActive) {
                val hint = if (editState.characterSuggestions.isEmpty())
                    "Enter to search · j/k to move sections"
                else
                    "↑↓ suggestions · Enter to accept · Enter on empty to search"
                Text(hint, style = MaterialTheme.typography.labelSmall, color = OnSurfaceMuted)
            }
        }
    }

    // ── Artists ───────────────────────────────────────────────────────────
    if (PendingCategory.ARTIST in pendingCategories) {
        Column(
            modifier = Modifier.fillMaxWidth().sectionHighlight(ReviewSection.ARTIST, kbState),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SectionHeader("Artists", null)
            if (editState.artistSuggestions.isNotEmpty()) {
                Text(
                    "Suggestions:",
                    style = MaterialTheme.typography.labelSmall,
                    color = OnSurfaceMuted,
                )
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    editState.artistSuggestions.forEachIndexed { index, s ->
                        val isHighlighted = kbState.focusedSection == ReviewSection.ARTIST &&
                                kbState.highlightedSuggestionIndex == index
                        SuggestionChip(
                            onClick = {
                                if (s.artistId != null) {
                                    val artist = ArtistDto(s.artistId, s.name ?: "")
                                    onUpdateEditState(editState.copy(artists = editState.artists + artist))
                                } else {
                                    onArtistQueryChange(s.name ?: "")
                                }
                            },
                            label = { Text("${s.name ?: ""} (${(s.confidence * 100).toInt()}%)") },
                            border = if (isHighlighted) FilterChipDefaults.filterChipBorder(
                                enabled = true,
                                selected = true,
                                borderColor = AccentTeal,
                                selectedBorderColor = AccentTeal,
                                borderWidth = 1.5.dp,
                                selectedBorderWidth = 1.5.dp,
                            ) else FilterChipDefaults.filterChipBorder(enabled = true, selected = false),
                        )
                    }
                }
            }
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                editState.artists.forEach { a ->
                    TagChip(
                        a.name,
                        onRemove = {
                            onUpdateEditState(
                                editState.copy(artists = editState.artists.filter { it.id != a.id })
                            )
                        },
                    )
                }
            }
            SearchableDropdown(
                label = "Search artist…",
                query = artistQuery,
                onQueryChange = onArtistQueryChange,
                results = artistResults,
                onSelect = { a ->
                    onUpdateEditState(editState.copy(artists = editState.artists + a))
                    onArtistQueryChange("")
                },
                itemLabel = { it.name },
                onCreateNew = onCreateArtist,
                highlightedIndex = if (kbState.focusedSection == ReviewSection.ARTIST && kbState.isSearchActive)
                    kbState.highlightedResultIndex else -1,
                focusRequester = artistFocusRequester,
            )
            if (kbState.focusedSection == ReviewSection.ARTIST && !kbState.isSearchActive) {
                val hint = if (editState.artistSuggestions.isEmpty())
                    "Enter to search · j/k to move sections"
                else
                    "↑↓ suggestions · Enter to accept · Enter on empty to search"
                Text(hint, style = MaterialTheme.typography.labelSmall, color = OnSurfaceMuted)
            }
        }
    }

    // ── Source platform ───────────────────────────────────────────────────
    if (PendingCategory.SOURCE_PLATFORM in pendingCategories) {
        Column(
            modifier = Modifier.fillMaxWidth().sectionHighlight(ReviewSection.SOURCE_PLATFORM, kbState),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            SectionHeader(
                "Publication Platform",
                editState.publicationPlatformSuggestion?.let { "Suggested: ${it.name}" },
            )
            SourcePlatformSelector(
                selected = editState.publicationPlatform,
                api = api,
                onSelected = { onUpdateEditState(editState.copy(publicationPlatform = it)) },
            )
        }
    }

    submitError?.let {
        Text("Error: $it", color = RatingNSFW, style = MaterialTheme.typography.bodySmall)
    }

    OutlinedButton(
        onClick = onSkip,
        enabled = !isSubmitting,
        modifier = Modifier
            .fillMaxWidth()
            .then(
                if (kbState.focusedSection == ReviewSection.SKIP)
                    Modifier.border(1.5.dp, AccentTeal, RoundedCornerShape(50))
                else Modifier
            ),
    ) {
        if (isSubmitting) CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
        else Text(if (kbState.focusedSection == ReviewSection.SKIP) "↵ Skip" else "Skip")
    }

    Button(
        onClick = onSubmit,
        enabled = !isSubmitting,
        modifier = Modifier
            .fillMaxWidth()
            .then(
                if (kbState.focusedSection == ReviewSection.SUBMIT)
                    Modifier.border(1.5.dp, AccentTeal, RoundedCornerShape(50))
                else Modifier
            ),
    ) {
        if (isSubmitting) CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
        else Text(if (kbState.focusedSection == ReviewSection.SUBMIT) "↵ Confirm & Next" else "Confirm & Next")
    }
}
