from datetime import datetime

from pydantic import BaseModel, Field


# ── Create / Input schemas ─────────────────────────────────────────────────────

class SeriesCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    series_id: int


class ArtistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ArtworkTagPatch(BaseModel):
    content_rating: str | None = None
    art_type: str | None = None
    characters: list[int] | None = None
    artists: list[int] | None = None
    publication_platform_id: int | None = None


class QueueCompleteRequest(BaseModel):
    characters: list[int] | None = None
    artists: list[int] | None = None
    publication_platform_id: int | None = None
    content_rating: str | None = None
    art_type: str | None = None


# ── Base output schemas ────────────────────────────────────────────────────────

class SeriesOut(BaseModel):
    id: int
    name: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SourcePlatformOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class CharacterOut(BaseModel):
    id: int
    name: str
    series: SeriesOut
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ArtistOut(BaseModel):
    id: int
    name: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Knowledge graph list responses ────────────────────────────────────────────

class SeriesWithCounts(BaseModel):
    id: int
    name: str
    character_count: int
    artwork_count: int

    model_config = {"from_attributes": True}


class SeriesListResponse(BaseModel):
    items: list[SeriesWithCounts]


class CharacterWithCount(BaseModel):
    id: int
    name: str
    series: SeriesOut
    artwork_count: int

    model_config = {"from_attributes": True}


class CharacterListResponse(BaseModel):
    items: list[CharacterWithCount]


class SeriesCharactersResponse(BaseModel):
    series: SeriesOut
    characters: list[CharacterWithCount]


class ArtistWithCount(BaseModel):
    id: int
    name: str
    artwork_count: int

    model_config = {"from_attributes": True}


class ArtistListResponse(BaseModel):
    items: list[ArtistWithCount]


# ── Gallery schemas ────────────────────────────────────────────────────────────

class ArtworkListItem(BaseModel):
    id: int
    file_url: str
    content_rating: str | None
    art_type: str | None
    series: list[SeriesOut]
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtworkListResponse(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[ArtworkListItem]


# ── Artwork detail schemas ─────────────────────────────────────────────────────

class CharacterWithSeries(BaseModel):
    id: int
    name: str
    series: SeriesOut
    confidence: float | None
    is_manual: bool

    model_config = {"from_attributes": True}


class ArtistWithConfidence(BaseModel):
    id: int
    name: str
    confidence: float | None
    is_manual: bool

    model_config = {"from_attributes": True}


class ArtworkDetail(BaseModel):
    id: int
    file_url: str
    content_rating: str | None
    content_rating_confidence: float | None
    content_rating_is_manual: bool
    art_type: str | None
    art_type_confidence: float | None
    art_type_is_manual: bool
    source_url: str
    source_platform_url: str | None
    publication_platform: SourcePlatformOut | None
    platform_context: dict | None
    characters: list[CharacterWithSeries]
    artists: list[ArtistWithConfidence]
    ingestion_timestamp: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArtworkTagPatchResponse(BaseModel):
    id: int
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Review queue schemas ───────────────────────────────────────────────────────

class TagSuggestion(BaseModel):
    name: str
    character_id: int | None = None
    artist_id: int | None = None
    confidence: float
    source: str  # "graph" | "slm" | "huggingface" | "ollama_vision"


class QueueSuggestions(BaseModel):
    characters: list[TagSuggestion] = []
    artists: list[TagSuggestion] = []
    content_rating: str | None = None
    content_rating_confidence: float | None = None
    art_type: str | None = None
    art_type_confidence: float | None = None
    publication_platform: TagSuggestion | None = None


class QueueCurrentTags(BaseModel):
    content_rating: str | None
    content_rating_confidence: float | None
    art_type: str | None
    art_type_confidence: float | None
    characters: list[CharacterWithSeries]
    artists: list[ArtistWithConfidence]
    publication_platform: SourcePlatformOut | None


class QueueArtwork(BaseModel):
    id: int
    file_url: str
    platform_context: dict | None
    source_url: str
    pending_categories: list[str]
    current_tags: QueueCurrentTags
    suggestions: QueueSuggestions


class QueueCount(BaseModel):
    count: int


class QueueCompleteResponse(BaseModel):
    id: int
    status: str
    file_path: str
    updated_at: datetime

    model_config = {"from_attributes": True}