import logging
import shutil
from pathlib import Path

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.models import Artwork, ArtworkCharacter, Character, Series

logger = logging.getLogger(__name__)


def resolve_review_destination(base_archive: Path, series_names: list[str]) -> Path:
    if len(series_names) > 1:
        return base_archive / "_multi_series"
    if len(series_names) == 1:
        return base_archive / series_names[0]
    return base_archive / "_pending"


def _current_series_names(db: Session, artwork_id: int) -> list[str]:
    """Return sorted list of series names currently tagged on an artwork."""
    rows = db.execute(
        select(distinct(Series.name))
        .join(Character, Character.series_id == Series.id)
        .join(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
        .where(ArtworkCharacter.artwork_id == artwork_id)
        .order_by(Series.name.asc())
    ).scalars().all()
    return list(rows)


def relocate_artwork_file(db: Session, artwork: Artwork, base_archive: Path) -> bool:
    """
    Move an artwork's file to the correct archive directory based on its
    current character tags. Updates artwork.file_path in the DB if moved.
    Does not commit — caller is responsible for committing.

    Called after any operation that may change an artwork's series membership:
      - Character tag changes (manual patch, bulk patch, queue completion)
      - Knowledge graph edits (character series reassignment, character/series
        deletion, series rename)

    Returns True if the file was moved, False if already correct or file missing.
    """
    current_path = Path(artwork.file_path)

    if not current_path.exists():
        logger.warning(
            "relocate_artwork_file: file missing on disk for artwork %d: %s",
            artwork.id, current_path,
        )
        artwork.file_missing = True
        return False

    series_names = _current_series_names(db, artwork.id)
    target_dir = resolve_review_destination(base_archive, series_names)
    target_path = target_dir / current_path.name

    if current_path.resolve() == target_path.resolve():
        return False  # Already in the right place

    target_dir.mkdir(parents=True, exist_ok=True)

    # Handle filename collision in target directory
    if target_path.exists() and target_path.resolve() != current_path.resolve():
        stem = target_path.stem
        suffix = target_path.suffix
        counter = 1
        while target_path.exists():
            target_path = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(str(current_path), str(target_path))
    logger.info(
        "Moved artwork %d: %s → %s",
        artwork.id, current_path, target_path,
    )
    artwork.file_path = str(target_path)
    artwork.file_missing = False
    return True