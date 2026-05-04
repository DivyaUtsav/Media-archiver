package com.mediaarchive.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.mediaarchive.data.api.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class TagEditState(
    val characters: List<CharacterTagDto> = emptyList(),
    val artists: List<ArtistTagDto> = emptyList(),
    val contentRating: String = "SFW",
    val artType: String = "Artwork",
    val publicationPlatform: SourcePlatformDto? = null,
)

data class ArtworkDetailState(
    val artwork: ArtworkDetailDto? = null,
    val isLoading: Boolean = false,
    val isEditing: Boolean = false,
    val editState: TagEditState? = null,
    val isSaving: Boolean = false,
    val saveError: String? = null,
    val error: String? = null,
)

class ArtworkDetailViewModel(private val api: ApiClient, private val artworkId: Int) : ViewModel() {

    private val _state = MutableStateFlow(ArtworkDetailState())
    val state: StateFlow<ArtworkDetailState> = _state

    init { load() }

    fun load() {
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null)
            try {
                val artwork = api.getArtwork(artworkId)
                _state.value = _state.value.copy(isLoading = false, artwork = artwork)
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }

    fun startEditing() {
        val artwork = _state.value.artwork ?: return
        _state.value = _state.value.copy(
            isEditing = true,
            editState = TagEditState(
                characters = artwork.characters,
                artists = artwork.artists,
                contentRating = artwork.contentRating ?: "SFW",
                artType = artwork.artType ?: "Artwork",
                publicationPlatform = artwork.publicationPlatform,
            ),
        )
    }

    fun cancelEditing() {
        _state.value = _state.value.copy(isEditing = false, editState = null, saveError = null)
    }

    fun updateEditState(editState: TagEditState) {
        _state.value = _state.value.copy(editState = editState)
    }

    fun saveTags() {
        val edit = _state.value.editState ?: return
        viewModelScope.launch {
            _state.value = _state.value.copy(isSaving = true, saveError = null)
            try {
                api.updateTags(
                    artworkId,
                    UpdateTagsRequest(
                        contentRating = edit.contentRating,
                        artType = edit.artType,
                        characters = edit.characters.map { it.id },
                        artists = edit.artists.map { it.id },
                        publicationPlatformId = edit.publicationPlatform?.id,
                    ),
                )
                _state.value = _state.value.copy(isSaving = false, isEditing = false, editState = null)
                load() // refresh
            } catch (e: Exception) {
                _state.value = _state.value.copy(isSaving = false, saveError = e.message)
            }
        }
    }

    fun createAndAddCharacter(name: String, seriesId: Int) {
        viewModelScope.launch {
            try {
                val newChar = api.createCharacter(name, seriesId)
                val cDto = CharacterTagDto(id = newChar.id, name = newChar.name, series = newChar.series!!, confidence = null, isManual = true)
                val edit = _state.value.editState
                if (edit != null) {
                    _state.value = _state.value.copy(editState = edit.copy(characters = edit.characters + cDto))
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(saveError = e.message)
            }
        }
    }

    fun createAndAddArtist(name: String) {
        viewModelScope.launch {
            try {
                val newArtist = api.createArtist(name)
                val aDto = ArtistTagDto(id = newArtist.id, name = newArtist.name, confidence = null, isManual = true)
                val edit = _state.value.editState
                if (edit != null) {
                    _state.value = _state.value.copy(editState = edit.copy(artists = edit.artists + aDto))
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(saveError = e.message)
            }
        }
    }
}
