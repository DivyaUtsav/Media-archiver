from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Artist, Artwork, ArtworkArtist, ArtworkCharacter, Character, Series, SourcePlatform
from app.schemas import ArtistCreate, ArtistOut, CharacterCreate, CharacterOut, SeriesCreate, SeriesOut

router = APIRouter(prefix="", tags=["knowledge-graph"])


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


@router.get("/characters")
def list_characters(
    search: str | None = Query(default=None),
    series_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
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
        stmt = stmt.where(func.lower(Character.name).like(f"{search.lower()}%"))
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
        "characters": [{"id": c.id, "name": c.name, "artwork_count": artwork_count} for c, artwork_count in counts],
    }


@router.get("/artists")
def list_artists(
    search: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
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
        stmt = stmt.where(func.lower(Artist.name).like(f"{search.lower()}%"))
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


@router.get("/source-platforms")
def list_source_platforms(db: Session = Depends(get_db)) -> dict:
    """Return all known source/publication platforms for use in Review Queue dropdowns."""
    rows = db.execute(select(SourcePlatform).order_by(SourcePlatform.name.asc())).scalars().all()
    return {"items": [{"id": row.id, "name": row.name} for row in rows]}
