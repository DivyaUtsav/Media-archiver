package com.mediaarchive.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mediaarchive.data.api.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class ReviewTagEditState(
    val characters: List<CharacterDto> = emptyList(),
    val characterSuggestions: List<TagSuggestionDto> = emptyList(),
    val artists: List<ArtistDto> = emptyList(),
    val artistSuggestions: List<TagSuggestionDto> = emptyList(),
    val contentRating: String? = null,
    val contentRatingSuggestion: String? = null,
    val artType: String? = null,
    val artTypeSuggestion: String? = null,
    val publicationPlatform: SourcePlatformDto? = null,
    val publicationPlatformSuggestion: TagSuggestionDto? = null,
)

data class ReviewQueueState(
    val currentArtwork: QueueArtworkDto? = null,
    val isLoading: Boolean = false,
    val queueCount: Int = 0,
    val pendingCategories: List<String> = emptyList(),
    val tagEditState: ReviewTagEditState = ReviewTagEditState(),
    val isSubmitting: Boolean = false,
    val submitError: String? = null,
    val error: String? = null,
    val isEmpty: Boolean = false,
)

class ReviewQueueViewModel(private val api: ApiClient) : ViewModel() {

    private val _state = MutableStateFlow(ReviewQueueState())
    val state: StateFlow<ReviewQueueState> = _state

    init { loadNext() }

    fun loadNext() {
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null, isEmpty = false, submitError = null)
            try {
                val count = api.getQueueCount()
                if (count.count == 0) {
                    _state.value = _state.value.copy(isLoading = false, isEmpty = true, queueCount = 0, currentArtwork = null)
                    return@launch
                }
                val artwork = api.getNextQueueItem()
                _state.value = _state.value.copy(
                    isLoading = false,
                    currentArtwork = artwork,
                    queueCount = count.count,
                    pendingCategories = artwork.pendingCategories,
                    tagEditState = buildInitialEditState(artwork),
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }

    private fun buildInitialEditState(artwork: QueueArtworkDto): ReviewTagEditState {
        val ct = artwork.currentTags
        val sg = artwork.suggestions
        return ReviewTagEditState(
            characters = ct.characters,
            characterSuggestions = sg.characters,
            artists = ct.artists,
            artistSuggestions = sg.artists,
            contentRating = ct.contentRating ?: (sg.contentRating?.name),
            contentRatingSuggestion = sg.contentRating?.name,
            artType = ct.artType ?: (sg.artType?.name),
            artTypeSuggestion = sg.artType?.name,
            publicationPlatform = ct.publicationPlatform,
            publicationPlatformSuggestion = sg.sourcePlatform,
        )
    }

    fun updateEditState(editState: ReviewTagEditState) {
        _state.value = _state.value.copy(tagEditState = editState)
    }

    /** Creates a character on the fly and immediately adds it to the edit state. */
    fun createAndAddCharacter(name: String, seriesId: Int) {
        viewModelScope.launch {
            try {
                val created = api.createCharacter(name, seriesId)
                val newChar = CharacterDto(id = created.id, name = created.name, seriesId = seriesId)
                val current = _state.value.tagEditState
                _state.value = _state.value.copy(
                    tagEditState = current.copy(characters = current.characters + newChar)
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(submitError = "Failed to create character: ${e.message}")
            }
        }
    }

    /** Creates an artist on the fly and immediately adds it to the edit state. */
    fun createAndAddArtist(name: String) {
        viewModelScope.launch {
            try {
                val created = api.createArtist(name)
                val newArtist = ArtistDto(id = created.id, name = created.name)
                val current = _state.value.tagEditState
                _state.value = _state.value.copy(
                    tagEditState = current.copy(artists = current.artists + newArtist)
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(submitError = "Failed to create artist: ${e.message}")
            }
        }
    }

    fun submit() {
        val artwork = _state.value.currentArtwork ?: return
        val edit = _state.value.tagEditState
        val pending = _state.value.pendingCategories
        viewModelScope.launch {
            _state.value = _state.value.copy(isSubmitting = true, submitError = null)
            try {
                api.completeQueueItem(
                    artwork.id,
                    CompleteQueueRequest(
                        characters = if ("character" in pending) edit.characters.map { it.id } else null,
                        artists = if ("artist" in pending) edit.artists.map { it.id } else null,
                        contentRating = if ("content_rating" in pending) edit.contentRating else null,
                        artType = if ("art_type" in pending) edit.artType else null,
                        publicationPlatformId = if ("source_platform" in pending) edit.publicationPlatform?.id else null,
                    ),
                )
                _state.value = _state.value.copy(isSubmitting = false)
                loadNext()
            } catch (e: Exception) {
                _state.value = _state.value.copy(isSubmitting = false, submitError = e.message)
            }
        }
    }
}
