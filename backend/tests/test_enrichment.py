import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Artwork, ArtworkPendingTag, Artist, Character, Series, SourcePlatform
from app.services.enrichment import run_enrichment
from app.services.enrichment_providers import ArtTypeResult, ContentRatingResult, TextExtractionResult, CharacterHint


class FakeTextProvider:
    def __init__(self, characters=None, artists=None, source_platform=None):
        # Accept both strings and CharacterHint objects for flexibility
        raw = characters or []
        self.characters = [
            c if isinstance(c, CharacterHint) else CharacterHint(name=c, series=None)
            for c in raw
        ]
        self.artists = artists or []
        self.source_platform = source_platform

    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        return TextExtractionResult(
            characters=self.characters,
            artists=self.artists,
            source_platform=self.source_platform,
        )


class FakeContentProvider:
    def __init__(self, value: str | None, confidence: float):
        self.value = value
        self.confidence = confidence

    def classify(self, image_path: Path, subreddit_is_nsfw: bool) -> ContentRatingResult:
        return ContentRatingResult(value=self.value, confidence=self.confidence, source="fake")


class FakeArtTypeProvider:
    def __init__(self, value: str | None, confidence: float):
        self.value = value
        self.confidence = confidence

    def classify(self, image_path: Path) -> ArtTypeResult:
        return ArtTypeResult(value=self.value, confidence=self.confidence, source="fake")


def test_enrichment_routes_to_pending_when_confidence_low(db_session: Session, tmp_path):
    settings.handoff_root = tmp_path / "handoff"
    settings.archive_root = tmp_path / "archive"
    settings.handoff_root.mkdir(parents=True, exist_ok=True)

    media = settings.handoff_root / "pending_case.jpg"
    media.write_bytes(b"img")
    sidecar = media.with_suffix(".jpg.json")
    sidecar.write_text(
        json.dumps(
            {
                "source_platform": "Reddit",
                "source_url": "https://reddit.com/post/pending-case",
                "source_platform_url": None,
                "platform_context": {"subreddit": "anime", "title": "unknown fanart", "flair": "Fanart"},
            }
        ),
        encoding="utf-8",
    )

    db_session.add(Artwork(file_path=str(media), source_url="https://reddit.com/post/pending-case", status="pending_review"))
    db_session.commit()

    stats = run_enrichment(
        db_session,
        text_provider=FakeTextProvider(),
        content_provider=FakeContentProvider(value="SFW", confidence=0.20),
        art_type_provider=FakeArtTypeProvider(value="Artwork", confidence=0.20),
    )
    assert stats.processed == 1
    assert stats.moved_to_pending == 1
    assert stats.moved_to_gallery == 0

    artwork = db_session.query(Artwork).filter(Artwork.source_url == "https://reddit.com/post/pending-case").one()
    assert artwork.status == "pending_review"
    assert "_pending" in artwork.file_path
    pending_tags = db_session.query(ArtworkPendingTag).filter(ArtworkPendingTag.artwork_id == artwork.id).all()
    assert len(pending_tags) >= 1


def test_enrichment_creates_graph_matches_and_gallery_route(db_session: Session, tmp_path):
    settings.handoff_root = tmp_path / "handoff"
    settings.archive_root = tmp_path / "archive"
    settings.handoff_root.mkdir(parents=True, exist_ok=True)

    series = Series(name="One Piece")
    character = Character(name="Zoro", series=series)
    db_session.add_all([series, character, SourcePlatform(name="Pixiv")])
    db_session.commit()

    media = settings.handoff_root / "gallery_case.jpg"
    media.write_bytes(b"img")
    sidecar = media.with_suffix(".jpg.json")
    sidecar.write_text(
        json.dumps(
            {
                "source_platform": "Reddit",
                "source_url": "https://reddit.com/post/gallery-case",
                "source_platform_url": "https://pixiv.net/en/artworks/123",
                "platform_context": {"subreddit": "OnePiece", "title": "Zoro fanart", "flair": "Fanart"},
            }
        ),
        encoding="utf-8",
    )

    db_session.add(Artwork(file_path=str(media), source_url="https://reddit.com/post/gallery-case", status="pending_review"))
    db_session.commit()

    stats = run_enrichment(
        db_session,
        text_provider=FakeTextProvider(characters=["Zoro"]),
        content_provider=FakeContentProvider(value="SFW", confidence=0.95),
        art_type_provider=FakeArtTypeProvider(value="Artwork", confidence=0.95),
    )

    assert stats.processed == 1
    assert stats.moved_to_gallery == 1

    artwork = db_session.query(Artwork).filter(Artwork.source_url == "https://reddit.com/post/gallery-case").one()
    assert artwork.status == "gallery"
    assert "One Piece" in Path(artwork.file_path).parts
