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


@dataclass
class IngestionStats:
    fetched: int = 0
    skipped_duplicates: int = 0
    dropped_to_handoff: int = 0


class IngestionAdapter(Protocol):
    def fetch_items(self) -> list[IngestionItem]:
        """Fetch new candidate media items from source platforms."""


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
    }
    sidecar_path.write_text(json.dumps(sidecar_payload, indent=2), encoding="utf-8")


def run_ingestion(db: Session, adapter: IngestionAdapter) -> IngestionStats:
    stats = IngestionStats()
    settings.handoff_root.mkdir(parents=True, exist_ok=True)

    for item in adapter.fetch_items():
        stats.fetched += 1
        if is_duplicate_source(db, item.source_url):
            stats.skipped_duplicates += 1
            continue

        source_platform = ensure_source_platform(db, item.source_platform_name or settings.default_source_platform)
        destination = settings.handoff_root / item.file_path.name
        if item.file_path.resolve() != destination.resolve():
            shutil.copy2(item.file_path, destination)
        sidecar = destination.with_suffix(f"{destination.suffix}.json")
        write_sidecar(sidecar, item)

        # Create initial record for downstream enrichment.
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
