from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session
from sqlalchemy import distinct, func, select, or_, exists

from app.database import get_db
from app.models import (
    Artwork,
    ArtworkArtist,
    ArtworkCharacter,
    Artist,
    Character,
    Series,
    SourcePlatform,
)
from app.schemas import ArtworkListItem, ArtworkListResponse, ArtworkTagPatch, ArtworkBulkPatch, ArtworkDetail, ArtworkTagPatchResponse
from app.services.storage import relocate_artwork_file
from app.config import settings

router = APIRouter(prefix="/artworks", tags=["artworks"])


def _replace_artwork_characters(db: Session, artwork_id: int, character_ids: list[int]) -> None:
    if character_ids:
        valid_ids = set(db.execute(select(Character.id).where(Character.id.in_(character_ids))).scalars().all())
        missing = sorted(set(character_ids) - valid_ids)
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown character ids: {missing}")
    db.query(ArtworkCharacter).where(ArtworkCharacter.artwork_id == artwork_id).delete()
    for character_id in character_ids:
        db.add(
            ArtworkCharacter(
                artwork_id=artwork_id,
                character_id=character_id,
                confidence=None,
                is_manual=True,
            )
        )


def _replace_artwork_artists(db: Session, artwork_id: int, artist_ids: list[int]) -> None:
    if artist_ids:
        valid_ids = set(db.execute(select(Artist.id).where(Artist.id.in_(artist_ids))).scalars().all())
        missing = sorted(set(artist_ids) - valid_ids)
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown artist ids: {missing}")
    db.query(ArtworkArtist).where(ArtworkArtist.artwork_id == artwork_id).delete()
    for artist_id in artist_ids:
        db.add(
            ArtworkArtist(
                artwork_id=artwork_id,
                artist_id=artist_id,
                confidence=None,
                is_manual=True,
            )
        )


def _series_for_artwork(db: Session, artwork_id: int) -> list[dict]:
    rows = db.execute(
        select(distinct(Series.id), Series.name)
        .join(Character, Character.series_id == Series.id)
        .join(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
        .where(ArtworkCharacter.artwork_id == artwork_id)
        .order_by(Series.name.asc())
    ).all()
    return [{"id": row[0], "name": row[1]} for row in rows]


@router.get("", response_model=ArtworkListResponse)
def list_artworks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    series_id: list[int] | None = Query(default=None),
    character_id: list[int] | None = Query(default=None),
    artist_id: list[int] | None = Query(default=None),
    content_rating: list[str] | None = Query(default=None),
    art_type: list[str] | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ArtworkListResponse:
    stmt = select(Artwork).where(Artwork.status == "gallery")
    if series_id or character_id:
        stmt = stmt.join(ArtworkCharacter, ArtworkCharacter.artwork_id == Artwork.id, isouter=True).join(
            Character, Character.id == ArtworkCharacter.character_id, isouter=True
        )
    if series_id:
        stmt = stmt.join(Series, Series.id == Character.series_id).where(Series.id.in_(series_id))
    if character_id:
        stmt = stmt.where(Character.id.in_(character_id))
    if artist_id:
        stmt = stmt.join(ArtworkArtist, ArtworkArtist.artwork_id == Artwork.id).where(ArtworkArtist.artist_id.in_(artist_id))
    if content_rating:
        stmt = stmt.where(Artwork.content_rating.in_(content_rating))
    if art_type:
        stmt = stmt.where(Artwork.art_type.in_(art_type))
    if search:
        pattern = f"%{search}%"
        character_match = exists(
            select(Character.id)
            .join(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
            .where(ArtworkCharacter.artwork_id == Artwork.id)
            .where(Character.name.ilike(pattern))
            .correlate(Artwork)
        )
        series_match = exists(
            select(Series.id)
            .join(Character, Character.series_id == Series.id)
            .join(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
            .where(ArtworkCharacter.artwork_id == Artwork.id)
            .where(Series.name.ilike(pattern))
            .correlate(Artwork)
        )
        artist_match = exists(
            select(Artist.id)
            .join(ArtworkArtist, ArtworkArtist.artist_id == Artist.id)
            .where(ArtworkArtist.artwork_id == Artwork.id)
            .where(Artist.name.ilike(pattern))
            .correlate(Artwork)
        )
        stmt = stmt.where(or_(character_match, series_match, artist_match))
    stmt = stmt.distinct()

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Artwork.ingestion_timestamp.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars()
    items = [
        ArtworkListItem(
            id=row.id,
            file_url=f"/artworks/{row.id}/media",
            content_rating=row.content_rating,
            art_type=row.art_type,
            series=_series_for_artwork(db, row.id),
            created_at=row.created_at,
        )
        for row in rows
    ]
    return ArtworkListResponse(page=page, page_size=page_size, total=total, items=items)


@router.get("/{artwork_id}", response_model=ArtworkDetail)
def get_artwork(artwork_id: int, db: Session = Depends(get_db)) -> ArtworkDetail:
    artwork = db.get(Artwork, artwork_id)
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found.")
    character_rows = db.execute(
        select(
            Character.id,
            Character.name,
            Series.id,
            Series.name,
            ArtworkCharacter.confidence,
            ArtworkCharacter.is_manual,
        )
        .join(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
        .join(Series, Series.id == Character.series_id)
        .where(ArtworkCharacter.artwork_id == artwork.id)
        .order_by(Character.name.asc())
    ).all()
    artist_rows = db.execute(
        select(Artist.id, Artist.name, ArtworkArtist.confidence, ArtworkArtist.is_manual)
        .join(ArtworkArtist, ArtworkArtist.artist_id == Artist.id)
        .where(ArtworkArtist.artwork_id == artwork.id)
        .order_by(Artist.name.asc())
    ).all()
    publication_platform = db.get(SourcePlatform, artwork.publication_platform_id) if artwork.publication_platform_id else None
    return {
        "id": artwork.id,
        "file_url": f"/artworks/{artwork.id}/media",
        "content_rating": artwork.content_rating,
        "content_rating_confidence": artwork.content_rating_confidence,
        "content_rating_is_manual": artwork.content_rating_is_manual,
        "art_type": artwork.art_type,
        "art_type_confidence": artwork.art_type_confidence,
        "art_type_is_manual": artwork.art_type_is_manual,
        "source_url": artwork.source_url,
        "source_platform_url": artwork.source_platform_url,
        "publication_platform": (
            {"id": publication_platform.id, "name": publication_platform.name} if publication_platform else None
        ),
        "platform_context": artwork.platform_context,
        "characters": [
            {
                "id": c_id,
                "name": c_name,
                "series": {"id": s_id, "name": s_name},
                "confidence": confidence,
                "is_manual": is_manual,
            }
            for c_id, c_name, s_id, s_name, confidence, is_manual in character_rows
        ],
        "artists": [
            {"id": a_id, "name": a_name, "confidence": confidence, "is_manual": is_manual}
            for a_id, a_name, confidence, is_manual in artist_rows
        ],
        "ingestion_timestamp": artwork.ingestion_timestamp,
        "created_at": artwork.created_at,
        "updated_at": artwork.updated_at,
    }


@router.get("/{artwork_id}/media")
def get_artwork_media(artwork_id: int, db: Session = Depends(get_db)) -> FileResponse:
    artwork = db.get(Artwork, artwork_id)
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found.")
    if artwork.file_missing:
        raise HTTPException(status_code=410, detail="Media file was previously recorded as missing.")
    media_path = Path(artwork.file_path)
    if not media_path.exists():
        # Mark the record so subsequent requests return 410 immediately.
        artwork.file_missing = True
        db.add(artwork)
        db.commit()
        raise HTTPException(status_code=410, detail="Media file is missing from disk.")
    return FileResponse(media_path)


@router.delete("/{artwork_id}")
def delete_artwork(artwork_id: int, db: Session = Depends(get_db)) -> dict:
    artwork = db.get(Artwork, artwork_id)
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found.")
    
    # Delete file from disk
    file_path = Path(artwork.file_path)
    if file_path.exists():
        file_path.unlink()
    
    # Delete record
    db.delete(artwork)
    db.commit()
    return {"id": artwork_id, "deleted": True}


@router.patch("/{artwork_id}/tags", response_model=ArtworkTagPatchResponse)
def patch_artwork_tags(artwork_id: int, payload: ArtworkTagPatch, db: Session = Depends(get_db)) -> ArtworkTagPatchResponse:
    artwork = db.get(Artwork, artwork_id)
    if not artwork:
        raise HTTPException(status_code=404, detail="Artwork not found.")

    if payload.content_rating is not None:
        artwork.content_rating = payload.content_rating
        artwork.content_rating_confidence = None
        artwork.content_rating_is_manual = True
    if payload.art_type is not None:
        artwork.art_type = payload.art_type
        artwork.art_type_confidence = None
        artwork.art_type_is_manual = True
    if payload.publication_platform_id is not None:
        if payload.publication_platform_id and not db.get(SourcePlatform, payload.publication_platform_id):
            raise HTTPException(status_code=400, detail="Unknown publication_platform_id.")
        artwork.publication_platform_id = payload.publication_platform_id
        artwork.publication_platform_confidence = None
        artwork.publication_platform_is_manual = True
    if payload.characters is not None:
        _replace_artwork_characters(db, artwork.id, payload.characters)
    if payload.artists is not None:
        _replace_artwork_artists(db, artwork.id, payload.artists)

    db.add(artwork)

    # Relocate file if characters changed — series membership may have shifted
    if payload.characters is not None:
        relocate_artwork_file(db, artwork, settings.archive_root)

    db.commit()
    db.refresh(artwork)
    return {"id": artwork.id, "updated_at": artwork.updated_at}


@router.patch("/bulk")
def patch_bulk_artworks(payload: ArtworkBulkPatch, db: Session = Depends(get_db)) -> dict:
    if not payload.artwork_ids:
        return {"updated_count": 0}

    artworks = db.execute(select(Artwork).where(Artwork.id.in_(payload.artwork_ids))).scalars().all()
    if not artworks:
        return {"updated_count": 0}

    for artwork in artworks:
        if payload.content_rating is not None:
            artwork.content_rating = payload.content_rating
            artwork.content_rating_confidence = None
            artwork.content_rating_is_manual = True
        if payload.art_type is not None:
            artwork.art_type = payload.art_type
            artwork.art_type_confidence = None
            artwork.art_type_is_manual = True
        if payload.publication_platform_id is not None:
            if payload.publication_platform_id and not db.get(SourcePlatform, payload.publication_platform_id):
                continue # Skip invalid
            artwork.publication_platform_id = payload.publication_platform_id
            artwork.publication_platform_confidence = None
            artwork.publication_platform_is_manual = True
        if payload.characters is not None:
            _replace_artwork_characters(db, artwork.id, payload.characters)
        if payload.artists is not None:
            _replace_artwork_artists(db, artwork.id, payload.artists)

        # Relocate file if characters changed — series membership may have shifted
        if payload.characters is not None:
            relocate_artwork_file(db, artwork, settings.archive_root)

        db.add(artwork)

    db.commit()
    return {"updated_count": len(artworks)}