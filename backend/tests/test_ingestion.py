"""
Tests for the ingestion service and adapters — covers ManifestIngestionAdapter,
GalleryDLIngestionAdapter metadata parsing, dedup logic, and sidecar writing.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Artwork, SourcePlatform
from app.services.ingestion import (
    IngestionItem,
    IngestionStats,
    ensure_source_platform,
    is_duplicate_source,
    run_ingestion,
    write_sidecar,
)
from app.services.ingestion_adapters import GalleryDLIngestionAdapter, ManifestIngestionAdapter


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_media(tmp_path: Path, name: str = "img.jpg") -> Path:
    p = tmp_path / name
    p.write_bytes(b"fake-image-data")
    return p


# ---------------------------------------------------------------------------
# ensure_source_platform
# ---------------------------------------------------------------------------


def test_ensure_source_platform_creates_new(db_session: Session):
    platform = ensure_source_platform(db_session, "Reddit")
    assert platform.id is not None
    assert platform.name == "Reddit"


def test_ensure_source_platform_idempotent(db_session: Session):
    p1 = ensure_source_platform(db_session, "Pixiv")
    p2 = ensure_source_platform(db_session, "Pixiv")
    assert p1.id == p2.id


# ---------------------------------------------------------------------------
# is_duplicate_source
# ---------------------------------------------------------------------------


def test_is_duplicate_source_false_when_absent(db_session: Session):
    assert not is_duplicate_source(db_session, "https://reddit.com/r/x/post/1")


def test_is_duplicate_source_true_when_present(db_session: Session, tmp_path: Path):
    media = _make_media(tmp_path)
    db_session.add(Artwork(file_path=str(media), source_url="https://reddit.com/r/x/post/dup", status="pending_review"))
    db_session.commit()
    assert is_duplicate_source(db_session, "https://reddit.com/r/x/post/dup")


# ---------------------------------------------------------------------------
# write_sidecar
# ---------------------------------------------------------------------------


def test_write_sidecar_produces_valid_json(tmp_path: Path):
    media = _make_media(tmp_path)
    item = IngestionItem(
        file_path=media,
        source_url="https://reddit.com/r/anime/post/abc",
        source_platform_url="https://pixiv.net/en/artworks/999",
        platform_context={"subreddit": "anime", "title": "Cool art", "flair": "Fanart"},
        source_platform_name="Reddit",
    )
    sidecar_path = media.with_suffix(".jpg.json")
    write_sidecar(sidecar_path, item)

    assert sidecar_path.exists()
    data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert data["source_url"] == item.source_url
    assert data["source_platform_url"] == item.source_platform_url
    assert data["source_platform"] == "Reddit"
    assert data["platform_context"]["subreddit"] == "anime"


# ---------------------------------------------------------------------------
# ManifestIngestionAdapter
# ---------------------------------------------------------------------------


def test_manifest_adapter_reads_entries(tmp_path: Path, db_session: Session):
    media = _make_media(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps([
            {
                "file_path": str(media),
                "source_url": "https://reddit.com/r/anime/post/m1",
                "source_platform_name": "Reddit",
                "platform_context": {"subreddit": "anime", "title": "Art", "flair": None},
            }
        ]),
        encoding="utf-8",
    )
    adapter = ManifestIngestionAdapter(manifest_path=manifest)
    items = adapter.fetch_items(db=db_session, batch_size=50)
    assert len(items) == 1
    assert items[0].source_url == "https://reddit.com/r/anime/post/m1"
    assert items[0].source_platform_name == "Reddit"
    assert items[0].platform_context["subreddit"] == "anime"


def test_manifest_adapter_returns_empty_when_missing(tmp_path: Path, db_session: Session):
    adapter = ManifestIngestionAdapter(manifest_path=tmp_path / "nonexistent.json")
    assert adapter.fetch_items(db=db_session, batch_size=50) == []


def test_manifest_adapter_uses_default_platform_when_absent(tmp_path: Path, db_session: Session):
    media = _make_media(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps([{"file_path": str(media), "source_url": "https://reddit.com/r/x/post/1"}]),
        encoding="utf-8",
    )
    settings.default_source_platform = "Reddit"
    adapter = ManifestIngestionAdapter(manifest_path=manifest)
    items = adapter.fetch_items(db=db_session, batch_size=50)
    assert items[0].source_platform_name == "Reddit"


# ---------------------------------------------------------------------------
# run_ingestion — integration
# ---------------------------------------------------------------------------


def test_run_ingestion_creates_db_record_and_sidecar(db_session: Session, tmp_path: Path):
    settings.handoff_root = tmp_path / "handoff"

    media = _make_media(tmp_path, "artwork.jpg")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps([
            {
                "file_path": str(media),
                "source_url": "https://reddit.com/r/anime/post/run1",
                "source_platform_name": "Reddit",
                "platform_context": {"subreddit": "anime", "title": "Test", "flair": None},
            }
        ]),
        encoding="utf-8",
    )

    adapter = ManifestIngestionAdapter(manifest_path=manifest)
    stats = run_ingestion(db_session, adapter)

    assert stats.fetched == 1
    assert stats.dropped_to_handoff == 1
    assert stats.skipped_duplicates == 0

    artwork = db_session.query(Artwork).filter(Artwork.source_url == "https://reddit.com/r/anime/post/run1").one()
    assert artwork.status == "pending_review"
    assert Path(artwork.file_path).exists()

    sidecar = Path(artwork.file_path).with_suffix(".jpg.json")
    assert sidecar.exists()


def test_run_ingestion_skips_duplicate(db_session: Session, tmp_path: Path):
    settings.handoff_root = tmp_path / "handoff"

    media = _make_media(tmp_path)
    url = "https://reddit.com/r/anime/post/dup99"
    db_session.add(Artwork(file_path=str(media), source_url=url, status="pending_review"))
    db_session.commit()

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps([{"file_path": str(media), "source_url": url, "source_platform_name": "Reddit", "platform_context": {}}]),
        encoding="utf-8",
    )
    adapter = ManifestIngestionAdapter(manifest_path=manifest)
    stats = run_ingestion(db_session, adapter)

    # Adapter handles dedup internally — run_ingestion sees 0 items fetched
    assert stats.fetched == 0
    assert stats.dropped_to_handoff == 0


# ---------------------------------------------------------------------------
# GalleryDLIngestionAdapter — unit tests for parsing helpers
# ---------------------------------------------------------------------------


class TestGalleryDLHelpers:
    adapter = GalleryDLIngestionAdapter()

    def test_resolve_source_url_from_permalink(self):
        meta = {"permalink": "/r/anime/comments/abc/cool_art/"}
        result = self.adapter._resolve_source_url(meta)
        assert result == "https://reddit.com/r/anime/comments/abc/cool_art/"

    def test_resolve_source_url_full_permalink(self):
        meta = {"permalink": "https://reddit.com/r/x/comments/xyz/"}
        assert self.adapter._resolve_source_url(meta) == "https://reddit.com/r/x/comments/xyz/"

    def test_resolve_source_url_fallback_to_url_key(self):
        meta = {"url": "https://i.redd.it/image.jpg"}
        assert self.adapter._resolve_source_url(meta) == "https://i.redd.it/image.jpg"

    def test_resolve_source_url_returns_none_when_absent(self):
        assert self.adapter._resolve_source_url({}) is None

    def test_resolve_source_platform_name_from_category(self):
        meta = {"category": "reddit"}
        assert self.adapter._resolve_source_platform_name(meta) == "Reddit"

    def test_resolve_source_platform_name_fallback(self):
        settings.default_source_platform = "Reddit"
        assert self.adapter._resolve_source_platform_name({}) == "Reddit"

    def test_build_platform_context_extracts_fields(self):
        meta = {"subreddit": "OnePiece", "title": "Zoro art", "link_flair_text": "Fanart"}
        ctx = self.adapter._build_platform_context(meta)
        assert ctx["subreddit"] == "OnePiece"
        assert ctx["title"] == "Zoro art"
        assert ctx["flair"] == "Fanart"

    def test_resolve_media_path_by_stripping_suffix(self, tmp_path: Path):
        media = tmp_path / "img.jpg"
        media.write_bytes(b"img")
        metadata_path = tmp_path / "img.jpg.json"
        metadata_path.write_text("{}", encoding="utf-8")
        result = self.adapter._resolve_media_path(metadata_path, {})
        assert result == media

    def test_resolve_media_path_returns_none_when_no_media(self, tmp_path: Path):
        metadata_path = tmp_path / "ghost.jpg.json"
        metadata_path.write_text("{}", encoding="utf-8")
        result = self.adapter._resolve_media_path(metadata_path, {})
        assert result is None

    def test_read_json_returns_none_on_invalid(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        assert self.adapter._read_json(bad) is None

    def test_read_json_returns_none_on_array(self, tmp_path: Path):
        arr = tmp_path / "arr.json"
        arr.write_text("[1,2,3]", encoding="utf-8")
        assert self.adapter._read_json(arr) is None
