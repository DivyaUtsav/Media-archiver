import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Artist,
    Artwork,
    ArtworkCharacter,
    ArtworkPendingTag,
    Character,
    Series,
    SourcePlatform,
)
from app.services.enrichment_providers import (
    ArtTypeProvider,
    ContentRatingProvider,
    TextExtractionProvider,
    get_art_type_provider,
    get_content_provider,
    get_text_provider,
)
from app.services.storage import resolve_review_destination

AUTO_TAG_MINIMUM = 0.80


@dataclass
class EnrichmentStats:
    processed: int = 0
    moved_to_gallery: int = 0
    moved_to_pending: int = 0


def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase.strip():
        return False
    pattern = rf"\b{re.escape(phrase.lower())}\b"
    return re.search(pattern, text.lower()) is not None


def _read_sidecar(sidecar_path: Path) -> dict | None:
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _get_or_create_platform(db: Session, name: str | None) -> SourcePlatform | None:
    if not name:
        return None
    existing = db.scalar(select(SourcePlatform).where(SourcePlatform.name == name))
    if existing:
        return existing
    created = SourcePlatform(name=name)
    db.add(created)
    db.flush()
    return created


def _match_graph_entities(db: Session, context_text: str) -> tuple[list[dict], list[dict], dict | None]:
    characters: list[dict] = []
    artists: list[dict] = []
    publication_platform: dict | None = None

    for character in db.execute(select(Character)).scalars().all():
        if _contains_phrase(context_text, character.name):
            characters.append({"name": character.name, "character_id": character.id, "confidence": 0.85, "source": "graph"})

    for artist in db.execute(select(Artist)).scalars().all():
        if _contains_phrase(context_text, artist.name):
            artists.append({"name": artist.name, "artist_id": artist.id, "confidence": 0.75, "source": "graph"})

    for platform in db.execute(select(SourcePlatform)).scalars().all():
        if _contains_phrase(context_text, platform.name):
            publication_platform = {
                "name": platform.name,
                "platform_id": platform.id,
                "confidence": 0.75,
                "source": "graph",
            }
            break

    return characters, artists, publication_platform


def _route_pending_categories(tags: dict) -> list[str]:
    pending_categories: list[str] = []

    # Characters — required. No characters = review queue.
    characters = tags["characters"]
    if not characters or any(item["confidence"] < AUTO_TAG_MINIMUM for item in characters):
        pending_categories.append("character")

    # Artists — flag if low confidence OR if any artist is unknown (no artist_id).
    # Unknown artists must go to review so the user can create them.
    artists = tags["artists"]
    if artists and (
        any(item["confidence"] < AUTO_TAG_MINIMUM for item in artists)
        or any(item.get("artist_id") is None for item in artists)
    ):
        pending_categories.append("artist")

    # Publication platform — optional, flag only if found but low confidence.
    platform = tags["publication_platform"]
    if platform and platform["confidence"] < AUTO_TAG_MINIMUM:
        pending_categories.append("source_platform")

    # Content rating — Suggestive always goes to review.
    rating = tags["content_rating"]
    if rating["value"] is None or rating["value"] == "Suggestive" or rating["confidence"] < AUTO_TAG_MINIMUM:
        pending_categories.append("content_rating")

    # Art type
    art_type = tags["art_type"]
    if art_type["value"] is None or art_type["confidence"] < AUTO_TAG_MINIMUM:
        pending_categories.append("art_type")

    return pending_categories


def _replace_pending(db: Session, artwork_id: int, tags: dict, pending_categories: list[str]) -> None:
    db.query(ArtworkPendingTag).where(ArtworkPendingTag.artwork_id == artwork_id).delete()
    for category in pending_categories:
        suggestion = None
        if category == "character":
            suggestion = tags["characters"]
        elif category == "artist":
            suggestion = tags["artists"]
        elif category == "source_platform":
            suggestion = tags["publication_platform"]
        elif category == "content_rating":
            suggestion = tags["content_rating"]
        elif category == "art_type":
            suggestion = tags["art_type"]
        db.add(ArtworkPendingTag(artwork_id=artwork_id, tag_category=category, suggestion=suggestion))


def _replace_artwork_characters(db: Session, artwork_id: int, characters: list[dict]) -> list[str]:
    db.query(ArtworkCharacter).where(ArtworkCharacter.artwork_id == artwork_id).delete()
    ids = []
    for item in characters:
        cid = item.get("character_id")
        if cid is None:
            continue
        ids.append(cid)
        db.add(ArtworkCharacter(artwork_id=artwork_id, character_id=cid, confidence=item["confidence"], is_manual=False))
    if not ids:
        return []
    rows = db.execute(select(Series.name).join(Character, Character.series_id == Series.id).where(Character.id.in_(ids))).all()
    return sorted({name for (name,) in rows})


def _replace_artwork_artists(db: Session, artwork_id: int, artists: list[dict]) -> None:
    from app.models import ArtworkArtist

    db.query(ArtworkArtist).where(ArtworkArtist.artwork_id == artwork_id).delete()
    for item in artists:
        aid = item.get("artist_id")
        if aid is None:
            continue
        db.add(ArtworkArtist(artwork_id=artwork_id, artist_id=aid, confidence=item["confidence"], is_manual=False))


def _find_character_by_name(db: Session, name: str) -> Character | None:
    return db.scalar(select(Character).where(Character.name.ilike(name)))


def _find_artist_by_name(db: Session, name: str) -> Artist | None:
    return db.scalar(select(Artist).where(Artist.name.ilike(name)))


def _find_platform_by_name(db: Session, name: str | None) -> SourcePlatform | None:
    if not name:
        return None
    return db.scalar(select(SourcePlatform).where(SourcePlatform.name.ilike(name)))


def run_enrichment(
    db: Session,
    text_provider: TextExtractionProvider | None = None,
    content_provider: ContentRatingProvider | None = None,
    art_type_provider: ArtTypeProvider | None = None,
) -> EnrichmentStats:
    stats = EnrichmentStats()
    settings.archive_root.mkdir(parents=True, exist_ok=True)
    (settings.archive_root / "_pending").mkdir(parents=True, exist_ok=True)
    text_provider = text_provider or get_text_provider(settings.enrichment_text_provider)
    content_provider = content_provider or get_content_provider(settings.enrichment_content_provider)
    art_type_provider = art_type_provider or get_art_type_provider(settings.enrichment_art_type_provider)

    for sidecar_path in settings.handoff_root.glob("*.json"):
        media_path = sidecar_path.with_suffix("")
        if not media_path.exists():
            continue
        sidecar = _read_sidecar(sidecar_path)
        if sidecar is None:
            continue

        source_url = sidecar.get("source_url")
        if not source_url:
            continue
        artwork = db.scalar(select(Artwork).where(Artwork.source_url == source_url))
        if not artwork:
            continue

        context = sidecar.get("platform_context") or {}

        # Build text blob from all available context fields — platform-agnostic.
        text_blob = " ".join(filter(None, [
            str(context.get("subreddit") or ""),
            str(context.get("title") or ""),
            str(context.get("flair") or ""),
            str(context.get("content") or ""),
            str(context.get("author") or ""),
        ]))

        graph_characters, graph_artists, publication_platform = _match_graph_entities(db, text_blob)

        try:
            extraction = text_provider.extract(
                subreddit=str(context.get("subreddit") or ""),
                title=str(context.get("title") or context.get("content") or ""),
                flair=str(context.get("flair") or ""),
                already_identified={"characters": [c["name"] for c in graph_characters], "artists": [a["name"] for a in graph_artists]},
            )
        except Exception:
            if settings.enrichment_strict_providers:
                raise
            extraction = get_text_provider("none").extract("", "", "", {})

        # Merge graph matches with SLM extractions — characters
        characters = list(graph_characters)
        known_character_names = {c["name"].lower() for c in characters}
        for name in extraction.characters:
            if not name or name.lower() in known_character_names:
                continue
            matched = _find_character_by_name(db, name)
            characters.append(
                {
                    "name": name,
                    "character_id": matched.id if matched else None,
                    "confidence": 0.65,
                    "source": "slm",
                }
            )

        # Merge graph matches with SLM extractions — artists
        artists = list(graph_artists)
        known_artist_names = {a["name"].lower() for a in artists}
        for name in extraction.artists:
            if not name or name.lower() in known_artist_names:
                continue
            matched_artist = _find_artist_by_name(db, name)
            artists.append(
                {
                    "name": name,
                    "artist_id": matched_artist.id if matched_artist else None,
                    "confidence": 0.70,
                    "source": "slm",
                }
            )
        if publication_platform is None and extraction.source_platform:
            matched_platform = _find_platform_by_name(db, extraction.source_platform)
            publication_platform = {
                "name": extraction.source_platform,
                "platform_id": matched_platform.id if matched_platform else None,
                "confidence": 0.75,
                "source": "slm",
            }

        # Platform-agnostic author auto-tagging.
        # Any platform that puts an "author" field in platform_context gets automatic
        # artist suggestion — Twitter, Reddit, Pixiv, all handled the same way.
        context_author = str(context.get("author") or "").strip()
        if context_author and context_author.lower() not in known_artist_names:
            matched_artist = _find_artist_by_name(db, context_author)
            artists.append({
                "name": context_author,
                "artist_id": matched_artist.id if matched_artist else None,
                # Known artists get graph confidence, unknown go to review
                "confidence": 0.85 if matched_artist else 0.80,
                "source": "graph" if matched_artist else "slm",
            })
            known_artist_names.add(context_author.lower())

        # Ensure ingestion source platform is recorded on artwork
        platform_name = sidecar.get("source_platform")
        platform_row = _get_or_create_platform(db, platform_name)
        if artwork.source_platform_id is None and platform_row:
            artwork.source_platform_id = platform_row.id

        # Also set publication_platform to ingestion source if not already determined.
        # This ensures artworks always have a publication platform recorded.
        if artwork.publication_platform_id is None and platform_row:
            artwork.publication_platform_id = platform_row.id
            artwork.publication_platform_confidence = 1.0
            artwork.publication_platform_is_manual = False

        # Content rating — use sensitive flag from platform_context as NSFW prior
        subreddit = str(context.get("subreddit") or "").lower()
        platform_sensitive = bool(context.get("sensitive", False))
        is_nsfw_context = platform_sensitive or any(
            flag in subreddit for flag in ("nsfw", "hentai", "rule34")
        )
        try:
            content_result = content_provider.classify(media_path, subreddit_is_nsfw=is_nsfw_context)
        except Exception:
            if settings.enrichment_strict_providers:
                raise
            content_result = get_content_provider("none").classify(media_path, subreddit_is_nsfw=False)

        try:
            art_type_result = art_type_provider.classify(media_path)
        except Exception:
            if settings.enrichment_strict_providers:
                raise
            art_type_result = get_art_type_provider("none").classify(media_path)
        content_rating = {"value": content_result.value, "confidence": content_result.confidence, "source": content_result.source}
        art_type = {"value": art_type_result.value, "confidence": art_type_result.confidence, "source": art_type_result.source}

        tags = {
            "characters": characters,
            "artists": artists,
            "publication_platform": publication_platform,
            "content_rating": content_rating,
            "art_type": art_type,
        }
        pending_categories = _route_pending_categories(tags)
        _replace_pending(db, artwork.id, tags, pending_categories)

        artwork.content_rating = content_rating["value"] if content_rating["value"] in {"SFW", "Suggestive", "NSFW"} else None
        artwork.content_rating_confidence = content_rating["confidence"]
        artwork.content_rating_is_manual = False
        artwork.art_type = art_type["value"] if art_type["value"] in {"Artwork", "Cosplay", "AI Generated"} else None
        artwork.art_type_confidence = art_type["confidence"]
        artwork.art_type_is_manual = False

        if publication_platform and publication_platform.get("platform_id"):
            artwork.publication_platform_id = publication_platform["platform_id"]
            artwork.publication_platform_confidence = publication_platform["confidence"]
            artwork.publication_platform_is_manual = False

        series_names = _replace_artwork_characters(db, artwork.id, characters)
        _replace_artwork_artists(db, artwork.id, artists)

        artwork.status = "pending_review" if pending_categories else "gallery"
        destination = resolve_review_destination(settings.archive_root, series_names if artwork.status == "gallery" else [])
        destination.mkdir(parents=True, exist_ok=True)
        final_media = destination / media_path.name

        try:
            shutil.move(str(media_path), str(final_media))
            sidecar_path.unlink(missing_ok=True)
            artwork.file_path = str(final_media)
            artwork.file_missing = False

            # Clean up original source file from ingestion_work if tracked
            original_path_str = sidecar.get("original_file_path")
            if original_path_str:
                original_path = Path(original_path_str)
                if original_path.exists() and original_path.resolve() != final_media.resolve():
                    original_path.unlink(missing_ok=True)

        except OSError:
            # Move failed — leave the file in the handoff dir and flag the record.
            artwork.file_missing = True

        stats.processed += 1
        if artwork.status == "gallery":
            stats.moved_to_gallery += 1
        else:
            stats.moved_to_pending += 1
        db.add(artwork)
        db.commit()

    return stats


def run_re_enrichment(db: Session) -> dict:
    """
    Re-runs graph matching on all pending_review artworks.
    Auto-resolves tag categories that now meet AUTO_TAG_MINIMUM
    after new characters/series/artists have been added to the knowledge graph.
    Only re-evaluates character, artist, and source_platform — skips
    content_rating and art_type since those are set by vision providers.
    """
    stats = {"processed": 0, "resolved": 0, "still_pending": 0}

    pending_artworks = db.execute(
        select(Artwork).where(Artwork.status == "pending_review")
    ).scalars().all()

    for artwork in pending_artworks:
        pending_categories = set(
            db.execute(
                select(ArtworkPendingTag.tag_category)
                .where(ArtworkPendingTag.artwork_id == artwork.id)
            ).scalars().all()
        )
        if not pending_categories:
            continue

        context = artwork.platform_context or {}
        text_blob = " ".join(filter(None, [
            str(context.get("subreddit") or ""),
            str(context.get("title") or ""),
            str(context.get("flair") or ""),
            str(context.get("content") or ""),
            str(context.get("author") or ""),
        ]))

        graph_characters, graph_artists, publication_platform = _match_graph_entities(db, text_blob)
        resolved_categories: set[str] = set()

        # Re-evaluate characters
        if "character" in pending_categories:
            if graph_characters and all(c["confidence"] >= AUTO_TAG_MINIMUM for c in graph_characters):
                _replace_artwork_characters(db, artwork.id, graph_characters)
                db.query(ArtworkPendingTag).filter(
                    ArtworkPendingTag.artwork_id == artwork.id,
                    ArtworkPendingTag.tag_category == "character",
                ).delete()
                resolved_categories.add("character")

        # Re-evaluate artists
        if "artist" in pending_categories:
            if graph_artists and all(
                a["confidence"] >= AUTO_TAG_MINIMUM and a.get("artist_id") is not None
                for a in graph_artists
            ):
                _replace_artwork_artists(db, artwork.id, graph_artists)
                db.query(ArtworkPendingTag).filter(
                    ArtworkPendingTag.artwork_id == artwork.id,
                    ArtworkPendingTag.tag_category == "artist",
                ).delete()
                resolved_categories.add("artist")

        # Re-evaluate publication platform
        if "source_platform" in pending_categories:
            if publication_platform and publication_platform["confidence"] >= AUTO_TAG_MINIMUM:
                artwork.publication_platform_id = publication_platform["platform_id"]
                artwork.publication_platform_confidence = publication_platform["confidence"]
                artwork.publication_platform_is_manual = False
                db.query(ArtworkPendingTag).filter(
                    ArtworkPendingTag.artwork_id == artwork.id,
                    ArtworkPendingTag.tag_category == "source_platform",
                ).delete()
                resolved_categories.add("source_platform")

        # If all pending categories resolved, move to gallery
        remaining = pending_categories - resolved_categories
        if not remaining:
            # Move file from _pending to correct destination
            current_path = Path(artwork.file_path)
            series_names = sorted({
                name for (name,) in db.execute(
                    select(Series.name)
                    .join(Character, Character.series_id == Series.id)
                    .join(ArtworkCharacter, ArtworkCharacter.character_id == Character.id)
                    .where(ArtworkCharacter.artwork_id == artwork.id)
                ).all()
            })
            destination = resolve_review_destination(settings.archive_root, series_names)
            destination.mkdir(parents=True, exist_ok=True)
            destination_path = destination / current_path.name
            if current_path.exists():
                shutil.move(str(current_path), str(destination_path))
                artwork.file_path = str(destination_path)
            artwork.status = "gallery"
            stats["resolved"] += 1
        else:
            stats["still_pending"] += 1

        stats["processed"] += 1
        db.add(artwork)
        db.commit()

    return stats