import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import requests

from app.config import settings


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class CharacterHint:
    """
    A character candidate extracted by a text provider.
    series is populated when the source provides reliable series context
    (e.g. Pixiv tags in Character(Series) format). None for Reddit/Twitter.
    """
    name: str
    series: str | None = None


@dataclass
class TextExtractionResult:
    characters: list[CharacterHint]
    artists: list[str]
    source_platform: str | None


@dataclass
class ContentRatingResult:
    value: str | None
    confidence: float
    source: str


@dataclass
class ArtTypeResult:
    value: str | None
    confidence: float
    source: str


# ── Provider protocols ─────────────────────────────────────────────────────────

class TextExtractionProvider(Protocol):
    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        """Return candidates with no guessing."""


class ContentRatingProvider(Protocol):
    def classify(self, image_path: Path, subreddit_is_nsfw: bool) -> ContentRatingResult:
        """Return rating and confidence."""


class ArtTypeProvider(Protocol):
    def classify(self, image_path: Path) -> ArtTypeResult:
        """Return art type and confidence."""


# ── Null providers ─────────────────────────────────────────────────────────────

class NullTextExtractionProvider:
    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        return TextExtractionResult(characters=[], artists=[], source_platform=None)


class NullContentRatingProvider:
    def classify(self, image_path: Path, subreddit_is_nsfw: bool) -> ContentRatingResult:
        return ContentRatingResult(value=None, confidence=0.0, source="none")


class NullArtTypeProvider:
    def classify(self, image_path: Path) -> ArtTypeResult:
        return ArtTypeResult(value=None, confidence=0.0, source="none")


# ── Reddit/Twitter Ollama text extraction ──────────────────────────────────────

class OllamaTextExtractionProvider:
    """
    Strict text extraction for Reddit and Twitter context.
    Extracts character names, artist credits, and source platform
    from subreddit name, post title, and flair.
    """

    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        prompt = (
            "You are a metadata extractor for anime, manga, and video game fanart.\n"
            "You will be given Reddit post information. Extract ONLY metadata you are\n"
            "confident about. If you are not sure, omit it entirely — do not guess.\n\n"
            "Rules:\n"
            "- characters: ONLY extract if a character name is explicitly stated in the\n"
            "  title or flair. Do not infer from subreddit alone.\n"
            "- artists: ONLY extract if there is an explicit credit (e.g. 'by ArtistName',\n"
            "  'art by', '[OC]' with a name, or a recognisable handle format).\n"
            "- source_platform: ONLY extract if a platform is explicitly named or linked\n"
            "  (e.g. 'Pixiv', 'Twitter', 'ArtStation'). Do not infer from URLs alone.\n"
            "- If a field has nothing confident to report, return empty list or null.\n"
            "- Do not repeat entities already identified (listed below).\n"
            "- Respond ONLY in JSON. No explanation, no preamble, no markdown.\n\n"
            f"Already identified: {json.dumps(already_identified)}\n\n"
            f"Subreddit: {subreddit}\n"
            f"Title: {title}\n"
            f"Flair: {flair}\n\n"
            'Response format:\n'
            '{"characters": ["name1", "name2"], "artists": ["name1"], "source_platform": null}'
        )
        response = requests.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.ollama_text_model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("response", "{}")
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)

        raw_characters = list(parsed.get("characters") or [])
        characters = []
        for c in raw_characters:
            name = c if isinstance(c, str) else c.get("name", "")
            if name:
                characters.append(CharacterHint(name=name, series=None))

        return TextExtractionResult(
            characters=characters,
            artists=[a if isinstance(a, str) else a.get("name", "") for a in list(parsed.get("artists") or [])],
            source_platform=parsed.get("source_platform"),
        )


# ── Pixiv Ollama text extraction ───────────────────────────────────────────────

class PixivOllamaTextExtractionProvider:
    """
    Strict text extraction for Pixiv illustrations.
    Pixiv tags are the primary signal — they often follow the pattern
    CharacterName(SeriesName) or CharacterName（SeriesName）in Japanese.
    Translates Japanese names to English where confident.
    Returns CharacterHint objects with series context when available.
    """

    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        # subreddit carries pixiv tags, title carries illustration title
        # this is set by the Pixiv adapter's platform_context mapping
        tags_raw = subreddit  # Pixiv adapter passes tags as the "subreddit" field
        illust_title = title

        prompt = (
            "You are extracting character and series names from Pixiv illustration tags.\n"
            "Pixiv tags often follow the pattern: CharacterName(SeriesName) or\n"
            "CharacterName（SeriesName）— both Western and Japanese bracket styles.\n\n"
            "Rules:\n"
            "- ONLY extract names that appear explicitly in the tags or title.\n"
            "- Translate Japanese names to English — only if you are confident in the translation.\n"
            "  If not confident, omit entirely. Do not guess.\n"
            "- For tags in the format Name(Series) or Name（Series）, extract both.\n"
            "- Ignore tags that are not character or series names (e.g. body part tags,\n"
            "  act descriptions, generic art style tags, view count tags like '1000users入り').\n"
            "- Do not repeat entries already identified.\n"
            "- If a field has nothing confident to report, return empty list.\n"
            "- Respond ONLY in JSON. No explanation, no preamble, no markdown.\n\n"
            f"Already identified: {json.dumps(already_identified)}\n\n"
            f"Tags: {tags_raw}\n"
            f"Title: {illust_title}\n\n"
            "Response format:\n"
            '{"characters": [{"name": "English name", "series": "English series or null"}], "artists": []}'
        )
        response = requests.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.ollama_text_model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("response", "{}")
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)

        raw_characters = list(parsed.get("characters") or [])
        characters = []
        for c in raw_characters:
            if isinstance(c, str):
                characters.append(CharacterHint(name=c, series=None))
            elif isinstance(c, dict):
                name = c.get("name", "").strip()
                series = c.get("series") or None
                if series:
                    series = series.strip() or None
                if name:
                    characters.append(CharacterHint(name=name, series=series))

        # Pixiv artist is always the uploader — extracted by the adapter, not the prompt
        # artists field intentionally empty here
        return TextExtractionResult(
            characters=characters,
            artists=[],
            source_platform="Pixiv",
        )


# ── HuggingFace content rating ─────────────────────────────────────────────────

class HuggingFaceContentRatingProvider:
    def __init__(self):
        from transformers import pipeline
        self._classifier = pipeline("image-classification", model=settings.huggingface_model)

    def classify(self, image_path: Path, subreddit_is_nsfw: bool) -> ContentRatingResult:
        predictions = self._classifier(str(image_path))
        safe_score = 0.0
        nsfw_score = 0.0
        for row in predictions:
            label = str(row.get("label", "")).lower()
            score = float(row.get("score", 0.0))
            if "normal" in label or "safe" in label:
                safe_score = max(safe_score, score)
            if "nsfw" in label:
                nsfw_score = max(nsfw_score, score)
        if subreddit_is_nsfw:
            nsfw_threshold, suggestive_threshold = 0.55, 0.30
        else:
            nsfw_threshold, suggestive_threshold = 0.75, 0.45
        if nsfw_score >= nsfw_threshold:
            return ContentRatingResult(value="NSFW", confidence=nsfw_score, source="huggingface")
        if nsfw_score >= suggestive_threshold:
            return ContentRatingResult(value="Suggestive", confidence=nsfw_score, source="huggingface")
        return ContentRatingResult(value="SFW", confidence=safe_score, source="huggingface")


# ── Ollama vision art type ─────────────────────────────────────────────────────

class OllamaArtTypeProvider:
    def classify(self, image_path: Path) -> ArtTypeResult:
        prompt = (
            "You are classifying a fanart image. Choose exactly one: "
            "Artwork (drawn/illustrated), Cosplay (real photo of person in costume), "
            "AI Generated (synthetic AI image). "
            "Respond with ONLY this JSON no other text: "
            "{\"art_type\": \"Artwork\", \"confidence\": 0.95}"
        )
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_vision_model,
                "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
                "stream": False,
            },
            timeout=180,
        )
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("message", {}).get("content", "{}")
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        return ArtTypeResult(
            value=parsed.get("art_type"),
            confidence=float(parsed.get("confidence", 0.0)),
            source="ollama_vision",
        )


# ── Provider factories ─────────────────────────────────────────────────────────

def get_text_provider(name: str) -> TextExtractionProvider:
    normalized = name.strip().lower()
    if normalized == "ollama":
        return OllamaTextExtractionProvider()
    if normalized == "ollama_pixiv":
        return PixivOllamaTextExtractionProvider()
    return NullTextExtractionProvider()


def get_content_provider(name: str) -> ContentRatingProvider:
    normalized = name.strip().lower()
    if normalized in {"huggingface", "hf"}:
        return HuggingFaceContentRatingProvider()
    return NullContentRatingProvider()


def get_art_type_provider(name: str) -> ArtTypeProvider:
    normalized = name.strip().lower()
    if normalized == "ollama":
        return OllamaArtTypeProvider()
    return NullArtTypeProvider()


# ── Health check ───────────────────────────────────────────────────────────────

def _check_ollama_model(model_name: str) -> tuple[bool, str]:
    try:
        response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=10)
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models") or []
        names = {str(row.get("name", "")) for row in models if isinstance(row, dict)}
        if any(name.startswith(model_name) or model_name.startswith(name) for name in names):
            return True, "available"
        return False, f"model '{model_name}' not found in Ollama tags"
    except Exception as exc:
        return False, f"ollama check failed: {exc}"


def provider_health_snapshot() -> dict:
    snapshot = {
        "text_provider": settings.enrichment_text_provider,
        "content_provider": settings.enrichment_content_provider,
        "art_type_provider": settings.enrichment_art_type_provider,
        "checks": {},
    }

    text_name = settings.enrichment_text_provider.strip().lower()
    if text_name in {"ollama", "ollama_pixiv"}:
        ok, detail = _check_ollama_model(settings.ollama_text_model)
        snapshot["checks"]["text"] = {"ok": ok, "detail": detail}
    else:
        snapshot["checks"]["text"] = {"ok": True, "detail": "disabled (provider=none)"}

    content_name = settings.enrichment_content_provider.strip().lower()
    if content_name in {"huggingface", "hf"}:
        try:
            import transformers  # noqa: F401
            snapshot["checks"]["content_rating"] = {"ok": True, "detail": "transformers import ok"}
        except Exception as exc:
            snapshot["checks"]["content_rating"] = {"ok": False, "detail": f"huggingface import failed: {exc}"}
    else:
        snapshot["checks"]["content_rating"] = {"ok": True, "detail": "disabled (provider=none)"}

    art_name = settings.enrichment_art_type_provider.strip().lower()
    if art_name == "ollama":
        ok, detail = _check_ollama_model(settings.ollama_vision_model)
        snapshot["checks"]["art_type"] = {"ok": ok, "detail": detail}
    else:
        snapshot["checks"]["art_type"] = {"ok": True, "detail": "disabled (provider=none)"}

    snapshot["ready"] = all(bool(check["ok"]) for check in snapshot["checks"].values())
    return snapshot