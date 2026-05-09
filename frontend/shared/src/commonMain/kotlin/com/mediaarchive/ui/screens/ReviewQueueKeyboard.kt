package com.mediaarchive.ui.screens

import com.mediaarchive.data.PendingCategory
import androidx.compose.ui.input.key.*
import com.mediaarchive.viewmodel.ReviewTagEditState
import com.mediaarchive.data.api.CharacterDto
import com.mediaarchive.data.api.ArtistDto
import com.mediaarchive.data.api.TagSuggestionDto

enum class ReviewSection {
    CONTENT_RATING,
    ART_TYPE,
    CHARACTER,
    ARTIST,
    SOURCE_PLATFORM,
    SUBMIT,
}

data class ReviewKeyboardState(
    val sections: List<ReviewSection> = emptyList(),
    val focusedSectionIndex: Int = 0,
    val highlightedSuggestionIndex: Int = -1,
    val highlightedResultIndex: Int = -1,
    val isSearchActive: Boolean = false,
) {
    val focusedSection: ReviewSection?
        get() = sections.getOrNull(focusedSectionIndex)
}

fun handleReviewKeyEvent(
    event: KeyEvent,
    kbState: ReviewKeyboardState,
    editState: ReviewTagEditState,
    characterResults: List<CharacterDto>,
    artistResults: List<ArtistDto>,
    characterQuery: String,
    artistQuery: String,
    onKbState: (ReviewKeyboardState) -> Unit,
    onUpdateEditState: (ReviewTagEditState) -> Unit,
    onCharacterQueryChange: (String) -> Unit,
    onArtistQueryChange: (String) -> Unit,
    onSubmit: () -> Unit,
    onBack: () -> Unit,
    isSubmitting: Boolean,
): Boolean {
    // On KeyDown, consume keys we own so Compose focus traversal doesn't steal them.
// On KeyUp, do the actual work. Anything else (KeyDown for unowned keys) falls through.
    if (event.type == KeyEventType.KeyDown) {
        val isNav = event.key in setOf(
            Key.DirectionUp, Key.DirectionDown, Key.DirectionLeft, Key.DirectionRight,
            Key.J, Key.K, Key.H, Key.L, Key.Enter, Key.Escape
        )
        // In search mode, only claim up/down/enter — let letters reach the TextField
        return if (kbState.isSearchActive) {
            event.key in setOf(Key.DirectionUp, Key.DirectionDown, Key.J, Key.K, Key.Enter, Key.Escape)
        } else {
            isNav
        }
    }
    if (event.type != KeyEventType.KeyUp) return false

    val section = kbState.focusedSection ?: return false
    val isVimDown = !kbState.isSearchActive && event.key == Key.J
    val isVimUp = !kbState.isSearchActive && event.key == Key.K
    val isVimLeft = !kbState.isSearchActive && event.key == Key.H
    val isVimRight = !kbState.isSearchActive && event.key == Key.L
    val isDown = event.key == Key.DirectionDown || isVimDown
    val isUp = event.key == Key.DirectionUp || isVimUp
    val isLeft = event.key == Key.DirectionLeft || isVimLeft
    val isRight = event.key == Key.DirectionRight || isVimRight
    val isEnter = event.key == Key.Enter
    val isEscape = event.key == Key.Escape

    // ── Escape handling ───────────────────────────────────────────────────
    if (isEscape) {
        return when {
            kbState.isSearchActive -> {
                onCharacterQueryChange("")
                onArtistQueryChange("")
                onKbState(kbState.copy(isSearchActive = false, highlightedResultIndex = -1))
                true
            }
            else -> { onBack(); true }
        }
    }

    // ── Search active — dropdown navigation ───────────────────────────────
    if (kbState.isSearchActive) {
        val query = if (section == ReviewSection.CHARACTER) characterQuery else artistQuery
        val onQueryChange = if (section == ReviewSection.CHARACTER) onCharacterQueryChange else onArtistQueryChange

        if (isDown) {
            val size = if (section == ReviewSection.CHARACTER) characterResults.size else artistResults.size
            val next = (kbState.highlightedResultIndex + 1).coerceAtMost(size - 1)
            onKbState(kbState.copy(highlightedResultIndex = next))
            return true
        }
        if (isUp) {
            val prev = (kbState.highlightedResultIndex - 1).coerceAtLeast(-1)
            onKbState(kbState.copy(highlightedResultIndex = prev))
            return true
        }
        if (isEnter) {
            val idx = kbState.highlightedResultIndex
            if (section == ReviewSection.CHARACTER) {
                if (idx >= 0 && idx < characterResults.size) {
                    val c = characterResults[idx]
                    onUpdateEditState(editState.copy(characters = editState.characters + c))
                    onCharacterQueryChange("")
                    onKbState(kbState.copy(isSearchActive = false, highlightedResultIndex = -1))
                }
            } else {
                if (idx >= 0 && idx < artistResults.size) {
                    val a = artistResults[idx]
                    onUpdateEditState(editState.copy(artists = editState.artists + a))
                    onArtistQueryChange("")
                    onKbState(kbState.copy(isSearchActive = false, highlightedResultIndex = -1))
                }
            }
            return true
        }
        return false // let other keys (letters) go to the text field naturally
    }

    // ── Section navigation (j/k) ──────────────────────────────────────────
    if (isDown) {
        val next = (kbState.focusedSectionIndex + 1).coerceAtMost(kbState.sections.size - 1)
        onKbState(kbState.copy(focusedSectionIndex = next, highlightedSuggestionIndex = -1))
        return true
    }
    if (isUp) {
        val prev = (kbState.focusedSectionIndex - 1).coerceAtLeast(0)
        onKbState(kbState.copy(focusedSectionIndex = prev, highlightedSuggestionIndex = -1))
        return true
    }

    // ── Rating / ArtType — h/l cycles options ─────────────────────────────
    if (section == ReviewSection.CONTENT_RATING) {
        val options = listOf("SFW", "Suggestive", "NSFW")
        val current = options.indexOf(editState.contentRating).takeIf { it >= 0 } ?: 0
        if (isRight) {
            onUpdateEditState(editState.copy(contentRating = options[(current + 1) % options.size]))
            return true
        }
        if (isLeft) {
            onUpdateEditState(editState.copy(contentRating = options[(current - 1 + options.size) % options.size]))
            return true
        }
        if (isEnter) {
            val next = (kbState.focusedSectionIndex + 1).coerceAtMost(kbState.sections.size - 1)
            onKbState(kbState.copy(focusedSectionIndex = next))
            return true
        }
    }

    if (section == ReviewSection.ART_TYPE) {
        val options = listOf("Artwork", "Cosplay", "AI Generated")
        val current = options.indexOf(editState.artType).takeIf { it >= 0 } ?: 0
        if (isRight) {
            onUpdateEditState(editState.copy(artType = options[(current + 1) % options.size]))
            return true
        }
        if (isLeft) {
            onUpdateEditState(editState.copy(artType = options[(current - 1 + options.size) % options.size]))
            return true
        }
        if (isEnter) {
            val next = (kbState.focusedSectionIndex + 1).coerceAtMost(kbState.sections.size - 1)
            onKbState(kbState.copy(focusedSectionIndex = next))
            return true
        }
    }

    // ── Character / Artist — suggestion navigation ────────────────────────
    if (section == ReviewSection.CHARACTER || section == ReviewSection.ARTIST) {
        val suggestions = if (section == ReviewSection.CHARACTER)
            editState.characterSuggestions else editState.artistSuggestions

        if (isRight || isDown) {
            if (suggestions.isNotEmpty()) {
                val next = (kbState.highlightedSuggestionIndex + 1).coerceAtMost(suggestions.size - 1)
                onKbState(kbState.copy(highlightedSuggestionIndex = next))
            }
            return true
        }
        if (isLeft || isUp) {
            if (suggestions.isNotEmpty()) {
                val prev = (kbState.highlightedSuggestionIndex - 1).coerceAtLeast(-1)
                onKbState(kbState.copy(highlightedSuggestionIndex = prev))
            }
            return true
        }
        if (isEnter) {
            val idx = kbState.highlightedSuggestionIndex
            if (idx >= 0 && idx < suggestions.size) {
                val s = suggestions[idx]
                if (section == ReviewSection.CHARACTER && s.characterId != null) {
                    val char = CharacterDto(s.characterId, s.name ?: "")
                    onUpdateEditState(editState.copy(characters = editState.characters + char))
                    onKbState(kbState.copy(highlightedSuggestionIndex = -1))
                } else if (section == ReviewSection.ARTIST && s.artistId != null) {
                    val artist = ArtistDto(s.artistId, s.name ?: "")
                    onUpdateEditState(editState.copy(artists = editState.artists + artist))
                    onKbState(kbState.copy(highlightedSuggestionIndex = -1))
                } else {
                    if (section == ReviewSection.CHARACTER)
                        onCharacterQueryChange(s.name ?: "")
                    else
                        onArtistQueryChange(s.name ?: "")
                    onKbState(kbState.copy(isSearchActive = true, highlightedResultIndex = -1))
                }
            } else {
                // Always activate search on Enter regardless of whether suggestions exist
                onKbState(kbState.copy(isSearchActive = true, highlightedResultIndex = -1))
            }
            return true
        }
    }

    // ── Submit section ────────────────────────────────────────────────────
    if (section == ReviewSection.SUBMIT && isEnter && !isSubmitting) {
        onSubmit()
        return true
    }

    return false
}

fun buildSectionList(pendingCategories: List<String>): List<ReviewSection> {
    val sections = mutableListOf<ReviewSection>()
    if (PendingCategory.CONTENT_RATING in pendingCategories) sections.add(ReviewSection.CONTENT_RATING)
    if (PendingCategory.ART_TYPE in pendingCategories) sections.add(ReviewSection.ART_TYPE)
    if (PendingCategory.CHARACTER in pendingCategories) sections.add(ReviewSection.CHARACTER)
    if (PendingCategory.ARTIST in pendingCategories) sections.add(ReviewSection.ARTIST)
    if (PendingCategory.SOURCE_PLATFORM in pendingCategories) sections.add(ReviewSection.SOURCE_PLATFORM)
    sections.add(ReviewSection.SUBMIT)
    return sections
}

