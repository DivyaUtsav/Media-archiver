from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    series: Mapped[Series] = relationship()


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class SourcePlatform(Base):
    __tablename__ = "source_platforms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


class Artwork(Base):
    __tablename__ = "artworks"
    __table_args__ = (
        CheckConstraint("content_rating IN ('SFW', 'Suggestive', 'NSFW')", name="chk_content_rating"),
        CheckConstraint("art_type IN ('Artwork', 'Cosplay', 'AI Generated')", name="chk_art_type"),
        CheckConstraint("status IN ('pending_review', 'gallery')", name="chk_status"),
        Index("idx_artworks_status", "status"),
        Index("idx_artworks_ingestion_timestamp", "ingestion_timestamp"),
        Index("idx_artworks_content_rating", "content_rating"),
        Index("idx_artworks_art_type", "art_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    source_platform_id: Mapped[int | None] = mapped_column(ForeignKey("source_platforms.id"))
    source_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source_platform_url: Mapped[str | None] = mapped_column(Text)
    characters: Mapped[list["ArtworkCharacter"]] = relationship(cascade="all, delete-orphan")
    artists: Mapped[list["ArtworkArtist"]] = relationship(cascade="all, delete-orphan")
    pending_tags: Mapped[list["ArtworkPendingTag"]] = relationship(cascade="all, delete-orphan")
    ingestion_timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    platform_context: Mapped[dict | None] = mapped_column(JSON)
    publication_platform_id: Mapped[int | None] = mapped_column(ForeignKey("source_platforms.id"))
    publication_platform_confidence: Mapped[float | None] = mapped_column(Float)
    publication_platform_is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    content_rating: Mapped[str | None] = mapped_column(String)
    content_rating_confidence: Mapped[float | None] = mapped_column(Float)
    content_rating_is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    art_type: Mapped[str | None] = mapped_column(String)
    art_type_confidence: Mapped[float | None] = mapped_column(Float)
    art_type_is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="pending_review")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    source_platform: Mapped[SourcePlatform | None] = relationship(foreign_keys=[source_platform_id])
    publication_platform: Mapped[SourcePlatform | None] = relationship(foreign_keys=[publication_platform_id])


class ArtworkCharacter(Base):
    __tablename__ = "artwork_characters"
    __table_args__ = (
        UniqueConstraint("artwork_id", "character_id", name="uq_artwork_character"),
        Index("idx_artwork_characters_artwork_id", "artwork_id"),
        Index("idx_artwork_characters_character_id", "character_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    artwork_id: Mapped[int] = mapped_column(ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class ArtworkArtist(Base):
    __tablename__ = "artwork_artists"
    __table_args__ = (
        UniqueConstraint("artwork_id", "artist_id", name="uq_artwork_artist"),
        Index("idx_artwork_artists_artwork_id", "artwork_id"),
        Index("idx_artwork_artists_artist_id", "artist_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    artwork_id: Mapped[int] = mapped_column(ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False)
    artist_id: Mapped[int] = mapped_column(ForeignKey("artists.id"), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class ArtworkPendingTag(Base):
    __tablename__ = "artwork_pending_tags"
    __table_args__ = (
        UniqueConstraint("artwork_id", "tag_category", name="uq_artwork_pending_category"),
        CheckConstraint(
            "tag_category IN ('character', 'artist', 'source_platform', 'content_rating', 'art_type')",
            name="chk_pending_tag_category",
        ),
        Index("idx_artwork_pending_artwork_id", "artwork_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    artwork_id: Mapped[int] = mapped_column(ForeignKey("artworks.id", ondelete="CASCADE"), nullable=False)
    tag_category: Mapped[str] = mapped_column(String, nullable=False)
    suggestion: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
