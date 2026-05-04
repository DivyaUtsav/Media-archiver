package com.mediaarchive.data.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ── Knowledge Graph ──────────────────────────────────────────────────────────

@Serializable
data class SeriesDto(
    val id: Int,
    val name: String,
    @SerialName("character_count") val characterCount: Int = 0,
    @SerialName("artwork_count") val artworkCount: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable
data class CharacterDto(
    val id: Int,
    val name: String,
    @SerialName("series_id") val seriesId: Int? = null,
    val series: SeriesDto? = null,
    @SerialName("artwork_count") val artworkCount: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable
data class ArtistDto(
    val id: Int,
    val name: String,
    @SerialName("artwork_count") val artworkCount: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable
data class SourcePlatformDto(val id: Int, val name: String)

@Serializable
data class SeriesListDto(val items: List<SeriesDto>)

@Serializable
data class CharacterListDto(val items: List<CharacterDto>)

@Serializable
data class ArtistListDto(val items: List<ArtistDto>)

@Serializable
data class SourcePlatformListDto(val items: List<SourcePlatformDto>)

// ── Gallery ──────────────────────────────────────────────────────────────────

@Serializable
data class ArtworkSummaryDto(
    val id: Int,
    @SerialName("file_url") val fileUrl: String,
    @SerialName("content_rating") val contentRating: String?,
    @SerialName("art_type") val artType: String?,
    val series: List<SeriesDto> = emptyList(),
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class ArtworkPageDto(
    val page: Int,
    @SerialName("page_size") val pageSize: Int,
    val total: Int,
    val items: List<ArtworkSummaryDto>,
)

@Serializable
data class CharacterTagDto(
    val id: Int,
    val name: String,
    val series: SeriesDto,
    val confidence: Double?,
    @SerialName("is_manual") val isManual: Boolean,
)

@Serializable
data class ArtistTagDto(
    val id: Int,
    val name: String,
    val confidence: Double?,
    @SerialName("is_manual") val isManual: Boolean,
)

@Serializable
data class ArtworkDetailDto(
    val id: Int,
    @SerialName("file_url") val fileUrl: String,
    @SerialName("content_rating") val contentRating: String?,
    @SerialName("content_rating_confidence") val contentRatingConfidence: Double?,
    @SerialName("content_rating_is_manual") val contentRatingIsManual: Boolean,
    @SerialName("art_type") val artType: String?,
    @SerialName("art_type_confidence") val artTypeConfidence: Double?,
    @SerialName("art_type_is_manual") val artTypeIsManual: Boolean,
    @SerialName("source_url") val sourceUrl: String,
    @SerialName("source_platform_url") val sourcePlatformUrl: String?,
    @SerialName("publication_platform") val publicationPlatform: SourcePlatformDto?,
    @SerialName("platform_context") val platformContext: PlatformContextDto?,
    val characters: List<CharacterTagDto>,
    val artists: List<ArtistTagDto>,
    @SerialName("ingestion_timestamp") val ingestionTimestamp: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

@Serializable
data class PlatformContextDto(
    val subreddit: String? = null,
    val title: String? = null,
    val flair: String? = null,
)

// ── Tag Patch ────────────────────────────────────────────────────────────────

@Serializable
data class UpdateTagsRequest(
    @SerialName("content_rating") val contentRating: String? = null,
    @SerialName("art_type") val artType: String? = null,
    val characters: List<Int>? = null,
    val artists: List<Int>? = null,
    @SerialName("publication_platform_id") val publicationPlatformId: Int? = null,
)

@Serializable
data class ArtworkBulkPatchRequest(
    @SerialName("artwork_ids") val artworkIds: List<Int>,
    @SerialName("content_rating") val contentRating: String? = null,
    @SerialName("art_type") val artType: String? = null,
    val characters: List<Int>? = null,
    val artists: List<Int>? = null,
    @SerialName("publication_platform_id") val publicationPlatformId: Int? = null,
)

@Serializable
data class UpdateTagsResponse(
    val id: Int,
    @SerialName("updated_at") val updatedAt: String,
)

// ── Review Queue ─────────────────────────────────────────────────────────────

@Serializable
data class QueueCountDto(@SerialName("count") val count: Int)

@Serializable
data class TagSuggestionDto(
    val name: String?,
    @SerialName("character_id") val characterId: Int? = null,
    @SerialName("artist_id") val artistId: Int? = null,
    @SerialName("platform_id") val platformId: Int? = null,
    val confidence: Double,
    val source: String,
)

@Serializable
data class QueueSuggestionsDto(
    val characters: List<TagSuggestionDto> = emptyList(),
    val artists: List<TagSuggestionDto> = emptyList(),
    @SerialName("content_rating") val contentRating: TagSuggestionDto? = null,
    @SerialName("art_type") val artType: TagSuggestionDto? = null,
    @SerialName("source_platform") val sourcePlatform: TagSuggestionDto? = null,
)

@Serializable
data class CurrentTagsDto(
    @SerialName("content_rating") val contentRating: String?,
    @SerialName("content_rating_confidence") val contentRatingConfidence: Double?,
    @SerialName("art_type") val artType: String?,
    @SerialName("art_type_confidence") val artTypeConfidence: Double?,
    val characters: List<CharacterDto>,
    val artists: List<ArtistDto>,
    @SerialName("publication_platform") val publicationPlatform: SourcePlatformDto?,
)

@Serializable
data class QueueArtworkDto(
    val id: Int,
    @SerialName("file_url") val fileUrl: String,
    @SerialName("platform_context") val platformContext: PlatformContextDto?,
    @SerialName("source_url") val sourceUrl: String,
    @SerialName("pending_categories") val pendingCategories: List<String>,
    @SerialName("current_tags") val currentTags: CurrentTagsDto,
    val suggestions: QueueSuggestionsDto,
)

@Serializable
data class CompleteQueueRequest(
    val characters: List<Int>? = null,
    val artists: List<Int>? = null,
    @SerialName("publication_platform_id") val publicationPlatformId: Int? = null,
    @SerialName("content_rating") val contentRating: String? = null,
    @SerialName("art_type") val artType: String? = null,
)

// ── Create requests ───────────────────────────────────────────────────────────

@Serializable
data class CreateSeriesRequest(val name: String)

@Serializable
data class CreateCharacterRequest(val name: String, @SerialName("series_id") val seriesId: Int)

@Serializable
data class CreateArtistRequest(val name: String)
