from pathlib import Path
import shutil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    Artwork,
    ArtworkArtist,
    ArtworkCharacter,
    ArtworkPendingTag,
    Artist,
    Character,
    Series,
    SourcePlatform,
)
from app.schemas import QueueCompleteRequest
from app.services.storage import resolve_review_destination
from app.services.enrichment import run_enrichment, run_re_enrichment


router = APIRouter(prefix="/queue", tags=["review-queue"])

def _require_pending_payload(payload: QueueCompleteRequest, pending_categories: set[str]) -> None:
    missing_fields: list[str] = []
    if "character" in pending_categories and payload.characters is None:
        missing_fields.append("characters")
    if "artist" in pending_categories and payload.artists is None:
        missing_fields.append("artists")
    if "source_platform" in pending_categories and payload.publication_platform_id is None:
        missing_fields.append("publication_platform_id")
    if "content_rating" in pending_categories and payload.content_rating is None:
        missing_fields.append("content_rating")
    if "art_type" in pending_categories and payload.art_type is None:
        missing_fields.append("art_type")
    if missing_fields:
        raise HTTPException(status_code=400, detail=f"Missing fields for pending categories: {missing_fields}")


def _replace_artwork_characters(db: Session, artwork_id: int, character_ids: list[int]) -> list[str]:
    valid_ids = set(db.execute(select(Character.id).where(Character.id.in_(character_ids))).scalars().all())
    missing = sorted(set(character_ids) - valid_ids)
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown character ids: {missing}")
    db.query(ArtworkCharacter).where(ArtworkCharacter.artwork_id == artwork_id).delete()
    for character_id in character_ids:
        db.add(ArtworkCharacter(artwork_id=artwork_id, character_id=character_id, confidence=None, is_manual=True))
    series_rows = db.execute(
        select(Series.name).join(Character, Character.series_id == Series.id).where(Character.id.in_(character_ids))
    ).all()
    return sorted({name for (name,) in series_rows})


def _replace_artwork_artists(db: Session, artwork_id: int, artist_ids: list[int]) -> None:
    valid_ids = set(db.execute(select(Artist.id).where(Artist.id.in_(artist_ids))).scalars().all())
    missing = sorted(set(artist_ids) - valid_ids)
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown artist ids: {missing}")
    db.query(ArtworkArtist).where(ArtworkArtist.artwork_id == artwork_id).delete()
    for artist_id in artist_ids:
        db.add(ArtworkArtist(artwork_id=artwork_id, artist_id=artist_id, confidence=None, is_manual=True))


@router.get("/count")
def get_queue_count(
    source_platform: str | None = Query(default=None),
    db: Session = Depends(get_db)
) -> dict:
    stmt = select(func.count()).select_from(Artwork).where(Artwork.status == "pending_review")
    if source_platform:
        stmt = (
            select(func.count())
            .select_from(Artwork)
            .join(SourcePlatform, SourcePlatform.id == Artwork.source_platform_id)
            .where(Artwork.status == "pending_review")
            .where(SourcePlatform.name.ilike(source_platform))
        )
    count = db.scalar(stmt) or 0
    return {"count": count}


@router.get("/next")
def get_next_pending_artwork(
    source_platform: str | None = Query(default=None),
    db: Session = Depends(get_db)
) -> dict:
    stmt = (
        select(Artwork)
        .where(Artwork.status == "pending_review")
        .order_by(Artwork.ingestion_timestamp.asc())
        .limit(1)
    )
    if source_platform:
        stmt = (
            select(Artwork)
            .join(SourcePlatform, SourcePlatform.id == Artwork.source_platform_id)
            .where(Artwork.status == "pending_review")
            .where(SourcePlatform.name.ilike(source_platform))
            .order_by(Artwork.ingestion_timestamp.asc())
            .limit(1)
        )
    artwork = db.execute(stmt).scalar_one_or_none()
    if not artwork:
        raise HTTPException(status_code=404, detail="No pending artworks.")

    pending = db.execute(
        select(ArtworkPendingTag).where(ArtworkPendingTag.artwork_id == artwork.id).order_by(ArtworkPendingTag.tag_category)
    ).scalars()
    suggestions: dict[str, list | dict] = {"characters": [], "artists": []}
    pending_categories: list[str] = []
    for row in pending:
        pending_categories.append(row.tag_category)
        if row.tag_category == "character":
            suggestions["characters"] = row.suggestion or []
        elif row.tag_category == "artist":
            suggestions["artists"] = row.suggestion or []
        else:
            raw = row.suggestion
            if raw and isinstance(raw, dict) and "value" in raw and "name" not in raw:
                # Normalize enrichment pipeline suggestions to use "name"
                raw = {**raw, "name": raw["value"]}
            suggestions[row.tag_category] = raw

    character_rows = db.execute(
        select(Character.id, Character.name, ArtworkCharacter.confidence, ArtworkCharacter.is_manual)
        .join(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
        .where(ArtworkCharacter.artwork_id == artwork.id)
    ).all()
    artist_rows = db.execute(
        select(Artist.id, Artist.name, ArtworkArtist.confidence, ArtworkArtist.is_manual)
        .join(ArtworkArtist, ArtworkArtist.artist_id == Artist.id)
        .where(ArtworkArtist.artwork_id == artwork.id)
    ).all()
    publication_platform = db.get(SourcePlatform, artwork.publication_platform_id) if artwork.publication_platform_id else None
    return {
        "id": artwork.id,
        "file_url": f"/artworks/{artwork.id}/media",
        "platform_context": artwork.platform_context,
        "source_url": artwork.source_url,
        "pending_categories": pending_categories,
        "current_tags": {
            "content_rating": artwork.content_rating,
            "content_rating_confidence": artwork.content_rating_confidence,
            "art_type": artwork.art_type,
            "art_type_confidence": artwork.art_type_confidence,
            "characters": [{"id": row[0], "name": row[1], "confidence": row[2], "is_manual": row[3]} for row in character_rows],
            "artists": [{"id": row[0], "name": row[1], "confidence": row[2], "is_manual": row[3]} for row in artist_rows],
            "publication_platform": (
                {"id": publication_platform.id, "name": publication_platform.name} if publication_platform else None
            ),
        },
        "suggestions": suggestions,
    }


@router.post("/re-enrich")
def re_enrich_pending(db: Session = Depends(get_db)) -> dict:
    stats = run_re_enrichment(db)
    return {
        "processed": stats["processed"],
        "resolved": stats["resolved"],
        "still_pending": stats["still_pending"]
    }

@router.post("/{artwork_id}/complete")
def complete_pending_artwork(artwork_id: int, payload: QueueCompleteRequest, db: Session = Depends(get_db)) -> dict:
    artwork = db.get(Artwork, artwork_id)
    if not artwork or artwork.status != "pending_review":
        raise HTTPException(status_code=404, detail="Pending artwork not found.")
    pending_categories = set(
        db.execute(select(ArtworkPendingTag.tag_category).where(ArtworkPendingTag.artwork_id == artwork.id)).scalars().all()
    )
    _require_pending_payload(payload, pending_categories)

    if payload.content_rating is not None:
        artwork.content_rating = payload.content_rating
        artwork.content_rating_confidence = None
        artwork.content_rating_is_manual = True
    if payload.art_type is not None:
        artwork.art_type = payload.art_type
        artwork.art_type_confidence = None
        artwork.art_type_is_manual = True
    if payload.publication_platform_id is not None:
        if not db.get(SourcePlatform, payload.publication_platform_id):
            raise HTTPException(status_code=400, detail="Unknown publication_platform_id.")
        artwork.publication_platform_id = payload.publication_platform_id
        artwork.publication_platform_confidence = None
        artwork.publication_platform_is_manual = True

    series_names: list[str] = []
    if payload.characters is not None:
        series_names = _replace_artwork_characters(db, artwork.id, payload.characters)
    if payload.artists is not None:
        _replace_artwork_artists(db, artwork.id, payload.artists)
    if not series_names:
        existing_series = db.execute(
            select(Series.name)
            .join(Character, Character.series_id == Series.id)
            .join(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
            .where(ArtworkCharacter.artwork_id == artwork.id)
        ).all()
        series_names = sorted({name for (name,) in existing_series})

    current_path = Path(artwork.file_path)
    destination_dir = resolve_review_destination(settings.archive_root, series_names)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / current_path.name
    if current_path.exists():
        shutil.move(str(current_path), str(destination_path))
        artwork.file_path = str(destination_path)

    db.query(ArtworkPendingTag).where(ArtworkPendingTag.artwork_id == artwork_id).delete()
    artwork.status = "gallery"
    db.add(artwork)
    db.commit()
    db.refresh(artwork)
    return {"id": artwork.id, "status": artwork.status, "file_path": artwork.file_path, "updated_at": artwork.updated_at}

@router.delete("/{artwork_id}")
def delete_pending_artwork(artwork_id: int, db: Session = Depends(get_db)) -> dict:
    artwork = db.get(Artwork, artwork_id)
    if not artwork or artwork.status != "pending_review":
        raise HTTPException(status_code=404, detail="Pending artwork not found.")
    
    # Delete file from disk
    file_path = Path(artwork.file_path)
    if file_path.exists():
        file_path.unlink()
    
    # Delete record — cascade handles artwork_pending_tags, artwork_characters, artwork_artists
    db.delete(artwork)
    db.commit()
    return {"id": artwork_id, "deleted": True}
