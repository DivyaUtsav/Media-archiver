import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from app.config import settings


@dataclass
class TextExtractionResult:
    characters: list[str]
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


class TextExtractionProvider(Protocol):
    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        """Return candidates with no guessing."""


class ContentRatingProvider(Protocol):
    def classify(self, image_path: Path, subreddit_is_nsfw: bool) -> ContentRatingResult:
        """Return rating and confidence."""


class ArtTypeProvider(Protocol):
    def classify(self, image_path: Path) -> ArtTypeResult:
        """Return art type and confidence."""


class NullTextExtractionProvider:
    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        return TextExtractionResult(characters=[], artists=[], source_platform=None)


class NullContentRatingProvider:
    def classify(self, image_path: Path, subreddit_is_nsfw: bool) -> ContentRatingResult:
        return ContentRatingResult(value=None, confidence=0.0, source="none")


class NullArtTypeProvider:
    def classify(self, image_path: Path) -> ArtTypeResult:
        return ArtTypeResult(value=None, confidence=0.0, source="none")


class OllamaTextExtractionProvider:
    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        prompt = (
            "You are a metadata extractor for anime, manga, and video game fanart.\n"
            "Extract ONLY confident metadata. If unsure, omit.\n"
            "Return JSON only in this format: "
            '{"characters":[],"artists":[],"source_platform":null}\n'
            f"Already identified: {json.dumps(already_identified)}\n"
            f"Subreddit: {subreddit}\nTitle: {title}\nFlair: {flair}\n"
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
        return TextExtractionResult(
            characters=[c if isinstance(c, str) else c.get("name", "") for c in list(parsed.get("characters") or [])],
            artists=[a if isinstance(a, str) else a.get("name", "") for a in list(parsed.get("artists") or [])],
            source_platform=parsed.get("source_platform"),
        )


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
        return ArtTypeResult(value=parsed.get("art_type"), confidence=float(parsed.get("confidence", 0.0)), source="ollama_vision")


def get_text_provider(name: str) -> TextExtractionProvider:
    normalized = name.strip().lower()
    if normalized == "ollama":
        return OllamaTextExtractionProvider()
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
    except Exception as exc:  # pragma: no cover - network failures are env-specific
        return False, f"ollama check failed: {exc}"


def provider_health_snapshot() -> dict:
    snapshot = {
        "text_provider": settings.enrichment_text_provider,
        "content_provider": settings.enrichment_content_provider,
        "art_type_provider": settings.enrichment_art_type_provider,
        "checks": {},
    }

    text_name = settings.enrichment_text_provider.strip().lower()
    if text_name == "ollama":
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
