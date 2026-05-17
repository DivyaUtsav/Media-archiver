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
    CharacterHint,
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


# ── Text utilities ─────────────────────────────────────────────────────────────

def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase.strip():
        return False
    pattern = rf"\b{re.escape(phrase.lower())}\b"
    return re.search(pattern, text.lower()) is not None


def _name_variants(name: str) -> list[str]:
    """
    Return name and its word-order reversal.
    Handles 'Mahiru Shiina' <-> 'Shiina Mahiru' matching.
    Only applies to two-word names — longer names are returned as-is.
    """
    parts = name.strip().split()
    if len(parts) == 2:
        return [name, f"{parts[1]} {parts[0]}"]
    return [name]


def _read_sidecar(sidecar_path: Path) -> dict | None:
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


# ── Database helpers ───────────────────────────────────────────────────────────

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


def _find_character_by_name(db: Session, name: str) -> Character | None:
    """
    Find a character by name, trying both word orderings.
    'Mahiru Shiina' will also check 'Shiina Mahiru'.
    """
    for variant in _name_variants(name):
        match = db.scalar(select(Character).where(Character.name.ilike(variant)))
        if match:
            return match
    return None


def _find_series_by_name(db: Session, name: str) -> Series | None:
    return db.scalar(select(Series).where(Series.name.ilike(name)))


def _find_artist_by_name(db: Session, name: str) -> Artist | None:
    return db.scalar(select(Artist).where(Artist.name.ilike(name)))


def _find_platform_by_name(db: Session, name: str | None) -> SourcePlatform | None:
    if not name:
        return None
    return db.scalar(select(SourcePlatform).where(SourcePlatform.name.ilike(name)))


def _try_auto_create_character(db: Session, hint: CharacterHint) -> Character | None:
    """
    Auto-create a character when:
    - The hint has a series name from a reliable source (e.g. Pixiv tags)
    - That series already exists in the knowledge graph
    - The character does not already exist (checked with name variants)
    Returns the created character, or None if conditions not met.
    """
    if not hint.series:
        return None
    series = _find_series_by_name(db, hint.series)
    if not series:
        return None
    # Check all name variants before creating to prevent duplicates
    existing = _find_character_by_name(db, hint.name)
    if existing:
        return existing
    new_character = Character(name=hint.name, series_id=series.id)
    db.add(new_character)
    db.flush()
    return new_character


# ── Graph matching ─────────────────────────────────────────────────────────────

def _match_graph_entities(
    db: Session, context_text: str
) -> tuple[list[dict], list[dict], dict | None]:
    characters: list[dict] = []
    artists: list[dict] = []
    publication_platform: dict | None = None

    for character in db.execute(select(Character)).scalars().all():
        # Try both name orderings against the context text
        for variant in _name_variants(character.name):
            if _contains_phrase(context_text, variant):
                characters.append({
                    "name": character.name,
                    "character_id": character.id,
                    "confidence": 0.85,
                    "source": "graph",
                })
                break  # Don't add same character twice

    for artist in db.execute(select(Artist)).scalars().all():
        if _contains_phrase(context_text, artist.name):
            artists.append({
                "name": artist.name,
                "artist_id": artist.id,
                "confidence": 0.75,
                "source": "graph",
            })

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


# ── Routing ────────────────────────────────────────────────────────────────────

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


# ── Pending tag management ─────────────────────────────────────────────────────

def _replace_pending(
    db: Session, artwork_id: int, tags: dict, pending_categories: list[str]
) -> None:
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
        db.add(ArtworkPendingTag(
            artwork_id=artwork_id,
            tag_category=category,
            suggestion=suggestion,
        ))


# ── Junction table management ──────────────────────────────────────────────────

def _replace_artwork_characters(
    db: Session, artwork_id: int, characters: list[dict]
) -> list[str]:
    db.query(ArtworkCharacter).where(ArtworkCharacter.artwork_id == artwork_id).delete()
    ids = []
    for item in characters:
        cid = item.get("character_id")
        if cid is None:
            continue
        ids.append(cid)
        db.add(ArtworkCharacter(
            artwork_id=artwork_id,
            character_id=cid,
            confidence=item["confidence"],
            is_manual=False,
        ))
    if not ids:
        return []
    rows = db.execute(
        select(Series.name)
        .join(Character, Character.series_id == Series.id)
        .where(Character.id.in_(ids))
    ).all()
    return sorted({name for (name,) in rows})


def _replace_artwork_artists(db: Session, artwork_id: int, artists: list[dict]) -> None:
    from app.models import ArtworkArtist

    db.query(ArtworkArtist).where(ArtworkArtist.artwork_id == artwork_id).delete()
    for item in artists:
        aid = item.get("artist_id")
        if aid is None:
            continue
        db.add(ArtworkArtist(
            artwork_id=artwork_id,
            artist_id=aid,
            confidence=item["confidence"],
            is_manual=False,
        ))


# ── Main enrichment pipeline ───────────────────────────────────────────────────

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
        source_platform_name = sidecar.get("source_platform", "")
        is_pixiv = source_platform_name.lower() == "pixiv"
        author_is_artist = bool(context.get("author_is_artist", False))

        # Only include author in the graph-matching text blob when the adapter
        # flagged them as the artist — prevents Reddit posters polluting artist matches
        author_text = str(context.get("author") or "") if author_is_artist else ""

        # Build text blob from all available context fields — platform-agnostic
        text_blob = " ".join(filter(None, [
            str(context.get("subreddit") or ""),
            str(context.get("title") or ""),
            str(context.get("flair") or ""),
            str(context.get("content") or ""),
            author_text,
            " ".join(context.get("tags") or []) if is_pixiv else "",
        ]))

        graph_characters, graph_artists, publication_platform = _match_graph_entities(db, text_blob)

        # Select the right text provider for this platform
        effective_text_provider = text_provider
        if is_pixiv:
            pixiv_provider_name = settings.enrichment_pixiv_text_provider
            if pixiv_provider_name and pixiv_provider_name.lower() != "none":
                effective_text_provider = get_text_provider(pixiv_provider_name)

        try:
            extraction = effective_text_provider.extract(
                subreddit=str(context.get("subreddit") or " ".join(context.get("tags") or [])),
                title=str(context.get("title") or context.get("content") or ""),
                flair=str(context.get("flair") or ""),
                already_identified={
                    "characters": [c["name"] for c in graph_characters],
                    "artists": [a["name"] for a in graph_artists],
                },
            )
        except Exception:
            if settings.enrichment_strict_providers:
                raise
            extraction = get_text_provider("none").extract("", "", "", {})

        # ── Merge characters ───────────────────────────────────────────────────
        characters = list(graph_characters)
        known_character_names: set[str] = set()
        for c in characters:
            for v in _name_variants(c["name"]):
                known_character_names.add(v.lower())

        for hint in extraction.characters:
            if not hint.name:
                continue
            already_known = any(
                v.lower() in known_character_names
                for v in _name_variants(hint.name)
            )
            if already_known:
                continue

            matched = _find_character_by_name(db, hint.name)

            if matched:
                characters.append({
                    "name": matched.name,
                    "character_id": matched.id,
                    "confidence": 0.75,
                    "source": "slm",
                })
                for v in _name_variants(matched.name):
                    known_character_names.add(v.lower())
            else:
                # Try auto-create for Pixiv when series hint is reliable
                auto_created = None
                if is_pixiv and hint.series:
                    auto_created = _try_auto_create_character(db, hint)

                if auto_created:
                    characters.append({
                        "name": auto_created.name,
                        "character_id": auto_created.id,
                        "confidence": 0.75,
                        "source": "slm",
                    })
                    for v in _name_variants(auto_created.name):
                        known_character_names.add(v.lower())
                else:
                    characters.append({
                        "name": hint.name,
                        "character_id": None,
                        "confidence": 0.65,
                        "source": "slm",
                        "series_hint": hint.series,
                    })
                    for v in _name_variants(hint.name):
                        known_character_names.add(v.lower())

        # ── Merge artists ──────────────────────────────────────────────────────
        artists = list(graph_artists)
        known_artist_names = {a["name"].lower() for a in artists}

        for name in extraction.artists:
            if not name or name.lower() in known_artist_names:
                continue
            matched_artist = _find_artist_by_name(db, name)
            if matched_artist:
                # Already in the knowledge graph — link with high confidence
                artists.append({
                    "name": matched_artist.name,
                    "artist_id": matched_artist.id,
                    "confidence": 0.85,
                    "source": "slm",
                })
            else:
                # SLM found an explicit credit (e.g. "by @handle") but we don't
                # know this artist yet — auto-create them so the artwork can be
                # fully tagged without manual intervention.
                new_artist = Artist(name=name)
                db.add(new_artist)
                db.flush()
                artists.append({
                    "name": new_artist.name,
                    "artist_id": new_artist.id,
                    "confidence": 0.80,
                    "source": "slm",
                })
            known_artist_names.add(name.lower())

        # Gemma 4 occasionally returns source_platform as a list — normalise to string
        raw_platform = extraction.source_platform
        if isinstance(raw_platform, list):
            raw_platform = raw_platform[0] if raw_platform else None
        if isinstance(raw_platform, str):
            raw_platform = raw_platform.strip() or None

        if publication_platform is None and raw_platform:
            matched_platform = _find_platform_by_name(db, raw_platform)
            # If SLM identified the same platform as ingestion source, it's reliable
            conf = 0.90 if (matched_platform and platform_row and matched_platform.id == platform_row.id) else 0.75
            publication_platform = {
                "name": raw_platform,
                "platform_id": matched_platform.id if matched_platform else None,
                "confidence": conf,
                "source": "slm",
            }

        # ── Author auto-tagging ────────────────────────────────────────────────
        # Only use context.author as the artist when the adapter explicitly
        # signals it (author_is_artist=True). Platforms like Twitter and Pixiv
        # set this because the poster is always the creator. Platforms like
        # Reddit do not — the poster may just be sharing someone else's work.
        context_author = str(context.get("author") or "").strip()
        author_is_artist = bool(context.get("author_is_artist", False))
        if author_is_artist and context_author and context_author.lower() not in known_artist_names:
            matched_artist = _find_artist_by_name(db, context_author)
            artists.append({
                "name": context_author,
                "artist_id": matched_artist.id if matched_artist else None,
                "confidence": 0.85 if matched_artist else 0.80,
                "source": "graph" if matched_artist else "slm",
            })
            known_artist_names.add(context_author.lower())

        # ── Pixiv metadata signals ─────────────────────────────────────────────
        x_restrict = int(context.get("x_restrict", 0))
        sanity_level = int(context.get("sanity_level", 2))
        illust_ai_type = int(context.get("illust_ai_type", 0))
        illust_type = str(context.get("type") or "")

        pixiv_art_type: str | None = None
        if is_pixiv:
            if illust_ai_type == 2:
                pixiv_art_type = "AI Generated"
            elif illust_type in {"illust", "manga", "ugoira"}:
                pixiv_art_type = "Artwork"

        # ── Source platform ────────────────────────────────────────────────────
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

        # For Pixiv, publication platform is always Pixiv with certainty —
        # set it in the tags dict so routing doesn't flag it as pending
        if is_pixiv and platform_row and publication_platform is None:
            publication_platform = {
                "name": platform_row.name,
                "platform_id": platform_row.id,
                "confidence": 1.0,
                "source": "pixiv_metadata",
            }

        # ── Content rating ─────────────────────────────────────────────────────
        subreddit = str(context.get("subreddit") or "").lower()
        platform_sensitive = bool(context.get("sensitive", False))
        pixiv_is_nsfw = is_pixiv and (x_restrict >= 1 or sanity_level >= 6)
        is_nsfw_context = platform_sensitive or pixiv_is_nsfw or any(
            flag in subreddit for flag in ("nsfw", "hentai", "rule34")
        )

        if is_pixiv and x_restrict >= 1:
            content_result_val: str | None = "NSFW"
            content_result_conf = 0.95 if x_restrict == 1 else 1.0
            content_result_src = "pixiv_metadata"
        elif is_pixiv and x_restrict == 0 and sanity_level <= 2:
            content_result_val = "SFW"
            content_result_conf = 0.90
            content_result_src = "pixiv_metadata"
        else:
            try:
                cr = content_provider.classify(media_path, subreddit_is_nsfw=is_nsfw_context)
                content_result_val = cr.value
                content_result_conf = cr.confidence
                content_result_src = cr.source
            except Exception:
                if settings.enrichment_strict_providers:
                    raise
                cr = get_content_provider("none").classify(media_path, subreddit_is_nsfw=False)
                content_result_val = cr.value
                content_result_conf = cr.confidence
                content_result_src = cr.source

        # ── Art type ───────────────────────────────────────────────────────────
        if is_pixiv and pixiv_art_type:
            art_type_val: str | None = pixiv_art_type
            art_type_conf = 0.95
            art_type_src = "pixiv_metadata"
        else:
            try:
                at = art_type_provider.classify(media_path)
                art_type_val = at.value
                art_type_conf = at.confidence
                art_type_src = at.source
            except Exception:
                if settings.enrichment_strict_providers:
                    raise
                at = get_art_type_provider("none").classify(media_path)
                art_type_val = at.value
                art_type_conf = at.confidence
                art_type_src = at.source

        content_rating = {
            "value": content_result_val,
            "confidence": content_result_conf,
            "source": content_result_src,
        }
        art_type = {
            "value": art_type_val,
            "confidence": art_type_conf,
            "source": art_type_src,
        }

        tags_dict = {
            "characters": characters,
            "artists": artists,
            "publication_platform": publication_platform,
            "content_rating": content_rating,
            "art_type": art_type,
        }
        pending_categories = _route_pending_categories(tags_dict)
        _replace_pending(db, artwork.id, tags_dict, pending_categories)

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
        destination = resolve_review_destination(
            settings.archive_root,
            series_names if artwork.status == "gallery" else [],
        )
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


# ── Re-enrichment ──────────────────────────────────────────────────────────────

def run_re_enrichment(db: Session) -> dict:
    """
    Re-runs graph matching on all pending_review artworks.
    Auto-resolves tag categories that now meet AUTO_TAG_MINIMUM
    after new characters/series/artists have been added to the knowledge graph.
    Only re-evaluates character, artist, and source_platform.
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
        source_platform = db.get(SourcePlatform, artwork.source_platform_id)
        is_pixiv = source_platform and source_platform.name.lower() == "pixiv"
        author_is_artist = bool(context.get("author_is_artist", False))

        # Only include author in the graph-matching text blob when the adapter
        # flagged them as the artist — prevents Reddit posters polluting artist matches
        author_text = str(context.get("author") or "") if author_is_artist else ""

        text_blob = " ".join(filter(None, [
            str(context.get("subreddit") or ""),
            str(context.get("title") or ""),
            str(context.get("flair") or ""),
            str(context.get("content") or ""),
            author_text,
            " ".join(context.get("tags") or []) if is_pixiv else "",
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

        # Re-evaluate artists — respects author_is_artist flag via text_blob above.
        # Graph matching only finds artists whose names appear in the text blob,
        # so Reddit posters are already excluded from graph_artists at this point.
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