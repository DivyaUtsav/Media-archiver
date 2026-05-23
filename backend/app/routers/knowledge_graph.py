from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Artist, Artwork, ArtworkArtist, ArtworkCharacter, Character, Series, SourcePlatform
from app.config import settings
from app.services.storage import relocate_artwork_file
from app.schemas import (
    ArtistCreate, ArtistOut, ArtistUpdate,
    CharacterCreate, CharacterOut, CharacterUpdate,
    SeriesCreate, SeriesOut, SeriesUpdate,
)

router = APIRouter(prefix="", tags=["knowledge-graph"])


# ── Series ────────────────────────────────────────────────────────────────────

@router.get("/series")
def list_series(db: Session = Depends(get_db)) -> dict:
    rows = (
        db.execute(
            select(
                Series.id,
                Series.name,
                func.count(func.distinct(Character.id)).label("character_count"),
                func.count(func.distinct(Artwork.id)).label("artwork_count"),
            )
            .outerjoin(Character, Character.series_id == Series.id)
            .outerjoin(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
            .outerjoin(Artwork, Artwork.id == ArtworkCharacter.artwork_id)
            .group_by(Series.id, Series.name)
            .order_by(Series.name.asc())
        )
        .all()
    )
    return {
        "items": [
            {
                "id": series_id,
                "name": name,
                "character_count": character_count,
                "artwork_count": artwork_count,
            }
            for series_id, name, character_count, artwork_count in rows
        ]
    }


@router.post("/series", response_model=SeriesOut, status_code=201)
def create_series(payload: SeriesCreate, db: Session = Depends(get_db)) -> SeriesOut:
    if db.scalar(select(Series).where(func.lower(Series.name) == payload.name.lower())):
        raise HTTPException(status_code=409, detail="Series already exists.")
    entity = Series(name=payload.name.strip())
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return SeriesOut(id=entity.id, name=entity.name, created_at=entity.created_at)


@router.patch("/series/{series_id}")
def update_series(series_id: int, payload: SeriesUpdate, db: Session = Depends(get_db)) -> dict:
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found.")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    conflict = db.scalar(
        select(Series)
        .where(func.lower(Series.name) == name.lower())
        .where(Series.id != series_id)
    )
    if conflict:
        raise HTTPException(status_code=409, detail="A series with that name already exists.")
    series.name = name
    db.add(series)
    db.flush()  # flush so _current_series_names sees the new name

    # Relocate all artworks that belong to this series — directory name changed
    affected_artwork_ids = db.execute(
        select(Artwork.id)
        .join(ArtworkCharacter, ArtworkCharacter.artwork_id == Artwork.id)
        .join(Character, Character.id == ArtworkCharacter.character_id)
        .where(Character.series_id == series_id)
        .where(Artwork.status == "gallery")
        .distinct()
    ).scalars().all()
    for artwork_id in affected_artwork_ids:
        artwork = db.get(Artwork, artwork_id)
        if artwork:
            relocate_artwork_file(db, artwork, settings.archive_root)

    db.commit()
    db.refresh(series)
    return {"id": series.id, "name": series.name}


@router.delete("/series/{series_id}")
def delete_series(series_id: int, db: Session = Depends(get_db)) -> dict:
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found.")
    character_count = db.scalar(
        select(func.count()).select_from(Character).where(Character.series_id == series_id)
    ) or 0
    if character_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: series has {character_count} character(s). Delete or move them first."
        )
    db.delete(series)
    db.commit()
    return {"id": series_id, "deleted": True}


# ── Characters ────────────────────────────────────────────────────────────────

@router.get("/characters")
def list_characters(
    search: str | None = Query(default=None),
    series_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict:
    stmt = (
        select(
            Character.id,
            Character.name,
            Series.id,
            Series.name,
            func.count(ArtworkCharacter.id).label("artwork_count"),
        )
        .join(Series, Series.id == Character.series_id)
        .outerjoin(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
        .group_by(Character.id, Series.id)
    )
    if search:
        stmt = stmt.where(
            func.lower(Character.name).like(f"%{search.lower()}%")
            | func.lower(Series.name).like(f"%{search.lower()}%")
        )
    if series_id:
        stmt = stmt.where(Character.series_id == series_id)
    rows = db.execute(stmt.order_by(Character.name.asc()).limit(limit)).all()
    return {
        "items": [
            {
                "id": char_id,
                "name": char_name,
                "series": {"id": series_id, "name": series_name},
                "artwork_count": artwork_count,
            }
            for char_id, char_name, series_id, series_name, artwork_count in rows
        ]
    }


@router.post("/characters", response_model=CharacterOut, status_code=201)
def create_character(payload: CharacterCreate, db: Session = Depends(get_db)) -> CharacterOut:
    series = db.get(Series, payload.series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found.")
    if db.scalar(select(Character).where(func.lower(Character.name) == payload.name.lower())):
        raise HTTPException(status_code=409, detail="Character already exists.")
    entity = Character(name=payload.name.strip(), series_id=payload.series_id)
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return CharacterOut(
        id=entity.id,
        name=entity.name,
        series=SeriesOut(id=series.id, name=series.name, created_at=series.created_at),
        created_at=entity.created_at,
    )


@router.patch("/characters/{character_id}")
def update_character(character_id: int, payload: CharacterUpdate, db: Session = Depends(get_db)) -> dict:
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found.")
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty.")
        conflict = db.scalar(
            select(Character)
            .where(func.lower(Character.name) == name.lower())
            .where(Character.id != character_id)
        )
        if conflict:
            raise HTTPException(status_code=409, detail="A character with that name already exists.")
        character.name = name
    if payload.series_id is not None:
        series = db.get(Series, payload.series_id)
        if not series:
            raise HTTPException(status_code=404, detail="Target series not found.")
        character.series_id = payload.series_id
    db.add(character)
    db.flush()  # flush so _current_series_names sees updated series_id

    # If series changed, relocate all artworks that have this character tagged
    if payload.series_id is not None:
        affected_artwork_ids = db.execute(
            select(Artwork.id)
            .join(ArtworkCharacter, ArtworkCharacter.artwork_id == Artwork.id)
            .where(ArtworkCharacter.character_id == character_id)
            .where(Artwork.status == "gallery")
            .distinct()
        ).scalars().all()
        for artwork_id in affected_artwork_ids:
            artwork = db.get(Artwork, artwork_id)
            if artwork:
                relocate_artwork_file(db, artwork, settings.archive_root)

    db.commit()
    db.refresh(character)
    series = db.get(Series, character.series_id)
    return {
        "id": character.id,
        "name": character.name,
        "series": {"id": series.id, "name": series.name},
    }


@router.delete("/characters/{character_id}")
def delete_character(character_id: int, db: Session = Depends(get_db)) -> dict:
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found.")
    artwork_count = db.scalar(
        select(func.count()).select_from(ArtworkCharacter)
        .where(ArtworkCharacter.character_id == character_id)
    ) or 0

    # Relocate affected artworks BEFORE removing tags — once tags are gone
    # _current_series_names won't know where they came from
    affected_artwork_ids = db.execute(
        select(Artwork.id)
        .join(ArtworkCharacter, ArtworkCharacter.artwork_id == Artwork.id)
        .where(ArtworkCharacter.character_id == character_id)
        .where(Artwork.status == "gallery")
        .distinct()
    ).scalars().all()

    # Remove all artwork tags for this character
    db.query(ArtworkCharacter).where(ArtworkCharacter.character_id == character_id).delete()
    db.flush()

    # Now relocate — with the tag removed, series membership recalculates correctly
    # (may now be _pending or _multi_series if other characters remain)
    for artwork_id in affected_artwork_ids:
        artwork = db.get(Artwork, artwork_id)
        if artwork:
            relocate_artwork_file(db, artwork, settings.archive_root)

    db.delete(character)
    db.commit()
    return {"id": character_id, "deleted": True, "artwork_tags_removed": artwork_count}


# ── Artists ───────────────────────────────────────────────────────────────────

@router.get("/artists")
def list_artists(
    search: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict:
    stmt = (
        select(
            Artist.id,
            Artist.name,
            func.count(ArtworkArtist.id).label("artwork_count"),
        )
        .outerjoin(ArtworkArtist, ArtworkArtist.artist_id == Artist.id)
        .group_by(Artist.id)
    )
    if search:
        stmt = stmt.where(func.lower(Artist.name).like(f"%{search.lower()}%"))
    rows = db.execute(stmt.order_by(Artist.name.asc()).limit(limit)).all()
    return {
        "items": [
            {"id": artist_id, "name": name, "artwork_count": artwork_count}
            for artist_id, name, artwork_count in rows
        ]
    }


@router.post("/artists", response_model=ArtistOut, status_code=201)
def create_artist(payload: ArtistCreate, db: Session = Depends(get_db)) -> ArtistOut:
    if db.scalar(select(Artist).where(func.lower(Artist.name) == payload.name.lower())):
        raise HTTPException(status_code=409, detail="Artist already exists.")
    entity = Artist(name=payload.name.strip())
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return ArtistOut(id=entity.id, name=entity.name, created_at=entity.created_at)


@router.patch("/artists/{artist_id}")
def update_artist(artist_id: int, payload: ArtistUpdate, db: Session = Depends(get_db)) -> dict:
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found.")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    conflict = db.scalar(
        select(Artist)
        .where(func.lower(Artist.name) == name.lower())
        .where(Artist.id != artist_id)
    )
    if conflict:
        raise HTTPException(status_code=409, detail="An artist with that name already exists.")
    artist.name = name
    db.add(artist)
    db.commit()
    db.refresh(artist)
    return {"id": artist.id, "name": artist.name}


@router.delete("/artists/{artist_id}")
def delete_artist(artist_id: int, db: Session = Depends(get_db)) -> dict:
    artist = db.get(Artist, artist_id)
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found.")
    artwork_count = db.scalar(
        select(func.count()).select_from(ArtworkArtist)
        .where(ArtworkArtist.artist_id == artist_id)
    ) or 0
    db.query(ArtworkArtist).where(ArtworkArtist.artist_id == artist_id).delete()
    db.delete(artist)
    db.commit()
    return {"id": artist_id, "deleted": True, "artwork_tags_removed": artwork_count}


# ── Series characters ─────────────────────────────────────────────────────────

@router.get("/series/{series_id}/characters")
def list_series_characters(series_id: int, db: Session = Depends(get_db)) -> dict:
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found.")
    counts = (
        db.execute(
            select(Character, func.count(ArtworkCharacter.id))
            .outerjoin(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
            .where(Character.series_id == series_id)
            .group_by(Character.id)
            .order_by(Character.name.asc())
        )
        .all()
    )
    return {
        "series": SeriesOut(id=series.id, name=series.name).model_dump(),
        "characters": [
            {"id": c.id, "name": c.name, "artwork_count": artwork_count}
            for c, artwork_count in counts
        ],
    }


# ── Source platforms ──────────────────────────────────────────────────────────

@router.get("/source-platforms")
def list_source_platforms(db: Session = Depends(get_db)) -> dict:
    """Return all known source/publication platforms for use in Review Queue dropdowns."""
    rows = db.execute(select(SourcePlatform).order_by(SourcePlatform.name.asc())).scalars().all()
    return {"items": [{"id": row.id, "name": row.name} for row in rows]}