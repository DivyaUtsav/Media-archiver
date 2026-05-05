import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Artwork, SourcePlatform


@dataclass
class IngestionItem:
    file_path: Path
    source_url: str
    source_platform_url: str | None
    platform_context: dict
    source_platform_name: str
    original_file_path: Path | None = None  # tracks source in ingestion_work for cleanup


@dataclass
class IngestionStats:
    fetched: int = 0
    skipped_duplicates: int = 0
    dropped_to_handoff: int = 0


class IngestionAdapter(Protocol):
    def fetch_items(self, db: Session, batch_size: int) -> list[IngestionItem]:
        """
        Fetch up to batch_size new media items from the source platform.
        Adapters are responsible for dedup checking against the database
        and stopping once batch_size new items have been found.
        """


def ensure_source_platform(db: Session, name: str) -> SourcePlatform:
    existing = db.scalar(select(SourcePlatform).where(SourcePlatform.name == name))
    if existing:
        return existing
    created = SourcePlatform(name=name)
    db.add(created)
    db.commit()
    db.refresh(created)
    return created


def is_duplicate_source(db: Session, source_url: str) -> bool:
    existing = db.scalar(select(Artwork.id).where(Artwork.source_url == source_url))
    return existing is not None


def write_sidecar(sidecar_path: Path, item: IngestionItem) -> None:
    sidecar_payload = {
        "source_platform": item.source_platform_name,
        "source_url": item.source_url,
        "source_platform_url": item.source_platform_url,
        "platform_context": item.platform_context,
        # Track original path in ingestion_work so enrichment can clean it up
        "original_file_path": str(item.original_file_path) if item.original_file_path else None,
    }
    sidecar_path.write_text(json.dumps(sidecar_payload, indent=2), encoding="utf-8")


def run_ingestion(db: Session, adapter: IngestionAdapter) -> IngestionStats:
    stats = IngestionStats()
    settings.handoff_root.mkdir(parents=True, exist_ok=True)

    # Adapters handle dedup and batch_size internally — run_ingestion just
    # processes whatever the adapter returns.
    for item in adapter.fetch_items(db=db, batch_size=settings.ingestion_batch_size):
        stats.fetched += 1

        source_platform = ensure_source_platform(
            db, item.source_platform_name or settings.default_source_platform
        )

        destination = settings.handoff_root / item.file_path.name
        if item.file_path.resolve() != destination.resolve():
            shutil.copy2(item.file_path, destination)

        sidecar = destination.with_suffix(f"{destination.suffix}.json")
        write_sidecar(sidecar, item)

        db.add(
            Artwork(
                file_path=str(destination),
                source_platform_id=source_platform.id,
                source_url=item.source_url,
                source_platform_url=item.source_platform_url,
                platform_context=item.platform_context,
                status="pending_review",
            )
        )
        db.commit()
        stats.dropped_to_handoff += 1

    return stats