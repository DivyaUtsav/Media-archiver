package com.mediaarchive.data.api

import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.plugins.logging.*
import io.ktor.client.request.*
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.serialization.json.Json

/** Platform-specific HTTP client factory. See desktopMain/androidMain. */
expect fun createPlatformHttpClient(json: Json): HttpClient

class ApiClient(private val baseUrl: () -> String) {

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
    }

    private val client = createPlatformHttpClient(json)

    // ── Gallery ──────────────────────────────────────────────────────────────

    suspend fun getArtworks(
        page: Int = 1,
        pageSize: Int = 50,
        seriesIds: List<Int> = emptyList(),
        characterIds: List<Int> = emptyList(),
        artistIds: List<Int> = emptyList(),
        contentRatings: List<String> = emptyList(),
        artTypes: List<String> = emptyList(),
    ): ArtworkPageDto = client.get("${baseUrl()}/artworks") {
        parameter("page", page)
        parameter("page_size", pageSize)
        seriesIds.forEach { parameter("series_id", it) }
        characterIds.forEach { parameter("character_id", it) }
        artistIds.forEach { parameter("artist_id", it) }
        contentRatings.forEach { parameter("content_rating", it) }
        artTypes.forEach { parameter("art_type", it) }
    }.body()

    suspend fun getArtwork(id: Int): ArtworkDetailDto =
        client.get("${baseUrl()}/artworks/$id").body()

    suspend fun updateTags(id: Int, request: UpdateTagsRequest): UpdateTagsResponse =
        client.patch("${baseUrl()}/artworks/$id/tags") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.body()

    suspend fun bulkUpdateTags(request: ArtworkBulkPatchRequest): Unit {
        client.patch("${baseUrl()}/artworks/bulk") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }
    }

    suspend fun deleteArtwork(id: Int) {
        client.delete("${baseUrl()}/artworks/$id")
    }

    /** Full URL for media — used directly by Coil. */
    fun mediaUrl(artworkId: Int): String = "${baseUrl()}/artworks/$artworkId/media"

    // ── Queue ────────────────────────────────────────────────────────────────

    suspend fun getQueueCount(sourcePlatform: String? = null): QueueCountDto =
        client.get("${baseUrl()}/queue/count") {
            sourcePlatform?.let { parameter("source_platform", it) }
        }.body()

    suspend fun getNextQueueItem(sourcePlatform: String? = null): QueueArtworkDto =
        client.get("${baseUrl()}/queue/next") {
            sourcePlatform?.let { parameter("source_platform", it) }
        }.body()

    suspend fun getQueuePlatforms(): QueuePlatformsResponse =
        client.get("${baseUrl()}/queue/platforms").body()

    suspend fun completeQueueItem(id: Int, request: CompleteQueueRequest): UpdateTagsResponse =
        client.post("${baseUrl()}/queue/$id/complete") {
            contentType(ContentType.Application.Json)
            setBody(request)
        }.body()

    suspend fun deletePendingArtwork(id: Int) {
        client.delete("${baseUrl()}/queue/$id")
    }

    // ── Knowledge Graph ───────────────────────────────────────────────────────

    suspend fun getSeries(): SeriesListDto =
        client.get("${baseUrl()}/series").body()

    suspend fun getSeriesCharacters(seriesId: Int): CharacterListDto =
        client.get("${baseUrl()}/series/$seriesId/characters").body()

    suspend fun searchCharacters(query: String, seriesId: Int? = null): CharacterListDto =
        client.get("${baseUrl()}/characters") {
            if (query.isNotBlank()) parameter("search", query)
            if (seriesId != null) parameter("series_id", seriesId)
            parameter("limit", 30)
        }.body()

    suspend fun searchArtists(query: String): ArtistListDto =
        client.get("${baseUrl()}/artists") {
            if (query.isNotBlank()) parameter("search", query)
            parameter("limit", 30)
        }.body()

    suspend fun getArtists(limit: Int = 100): ArtistListDto =
        client.get("${baseUrl()}/artists") {
            parameter("limit", limit)
        }.body()

    suspend fun getSourcePlatforms(): SourcePlatformListDto =
        client.get("${baseUrl()}/source-platforms").body()

    suspend fun createSeries(name: String): SeriesDto =
        client.post("${baseUrl()}/series") {
            contentType(ContentType.Application.Json)
            setBody(CreateSeriesRequest(name))
        }.body()

    suspend fun createCharacter(name: String, seriesId: Int): CharacterDto =
        client.post("${baseUrl()}/characters") {
            contentType(ContentType.Application.Json)
            setBody(CreateCharacterRequest(name, seriesId))
        }.body()

    suspend fun createArtist(name: String): ArtistDto =
        client.post("${baseUrl()}/artists") {
            contentType(ContentType.Application.Json)
            setBody(CreateArtistRequest(name))
        }.body()

    fun close() = client.close()
}
