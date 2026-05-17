import base64
import json
import re
from dataclasses import dataclass
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


# ── Shared Ollama JSON helper ──────────────────────────────────────────────────

def _ollama_generate(model: str, prompt: str, timeout: int = 120) -> str:
    """Call Ollama /api/generate and return the raw response string."""
    response = requests.post(
        f"{settings.ollama_base_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("response", "{}")


def _ollama_chat_vision(model: str, prompt: str, image_path: Path, timeout: int = 180) -> str:
    """Call Ollama /api/chat with an image and return the raw response string."""
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    response = requests.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
            "stream": False,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("message", {}).get("content", "{}")


def _parse_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON, returning empty dict on failure."""
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    # Gemma 4 sometimes wraps output in thinking blocks — strip them
    cleaned = re.sub(r"<\|channel\|>thought.*?<channel\|>", "", cleaned, flags=re.DOTALL).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try extracting the first JSON object if there's surrounding text
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


# ── Gemma4 text extraction (replaces OllamaTextExtractionProvider) ─────────────

class Gemma4TextExtractionProvider:
    """
    Text extraction using Gemma 4 E2B via Ollama.

    Handles multilingual content natively — Japanese character/series names
    from Pixiv tags are translated to English when the match is confident.
    Used for both Reddit/Twitter context and Pixiv tags (replacing the
    separate PixivOllamaTextExtractionProvider when configured).

    Set in .env:
        MEDIA_ARCHIVE_ENRICHMENT_TEXT_PROVIDER=gemma4
        MEDIA_ARCHIVE_ENRICHMENT_PIXIV_TEXT_PROVIDER=gemma4_pixiv
        MEDIA_ARCHIVE_OLLAMA_TEXT_MODEL=gemma4:e2b
    """

    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        prompt = (
            "You are a metadata extractor for anime, manga, and video game fanart.\n"
            "You will be given context signals about a piece of artwork — which may come\n"
            "from any platform (Reddit, Twitter, a fan site, etc). Extract ONLY metadata\n"
            "you are confident about. If you are not sure, omit it entirely — do not guess.\n\n"
            "Rules:\n"
            "- characters: ONLY extract if a character name is explicitly stated in the\n"
            "  title or flair/tags. Do not infer from the community/subreddit name alone.\n"
            "  If the name is in Japanese, translate it to English if you are confident.\n"
            "  If not confident in the translation, omit it.\n"
            "- artists: ONLY extract if there is an explicit credit in the title or flair\n"
            "  (e.g. 'by ArtistName', 'art by', '@handle', '[OC]' with a name).\n"
            "  Return the name only — strip any leading @ symbol.\n"
            "- source_platform: ONLY extract if a platform is explicitly named\n"
            "  (e.g. 'Pixiv', 'Twitter', 'ArtStation'). Do not infer from URLs alone.\n"
            "- If a field has nothing confident to report, return empty list or null.\n"
            "- Do not repeat entities already identified (listed below).\n"
            "- Respond ONLY with a JSON object. No explanation, no preamble, no markdown.\n\n"
            f"Already identified: {json.dumps(already_identified)}\n\n"
            f"Community/tags: {subreddit}\n"
            f"Title: {title}\n"
            f"Flair: {flair}\n\n"
            'Response format:\n'
            '{"characters": ["name1", "name2"], "artists": ["name1"], "source_platform": null}'
        )
        raw = _ollama_generate(settings.ollama_text_model, prompt)
        parsed = _parse_json(raw)

        raw_characters = list(parsed.get("characters") or [])
        characters = []
        for c in raw_characters:
            name = c if isinstance(c, str) else c.get("name", "")
            if name:
                characters.append(CharacterHint(name=name.strip(), series=None))

        raw_artists = [a if isinstance(a, str) else a.get("name", "") for a in list(parsed.get("artists") or [])]
        artists = [a.lstrip("@").strip() for a in raw_artists if a]

        return TextExtractionResult(
            characters=characters,
            artists=artists,
            source_platform=parsed.get("source_platform"),
        )


# ── Gemma4 Pixiv text extraction ───────────────────────────────────────────────

class Gemma4PixivTextExtractionProvider:
    """
    Pixiv-specific text extraction using Gemma 4 E2B.

    Handles Japanese Pixiv tags natively — CharacterName(SeriesName) pattern
    in both ASCII and full-width brackets, with Japanese → English translation.
    Significantly more accurate than qwen2.5 on non-Latin scripts.

    Set in .env:
        MEDIA_ARCHIVE_ENRICHMENT_PIXIV_TEXT_PROVIDER=gemma4_pixiv
        MEDIA_ARCHIVE_OLLAMA_TEXT_MODEL=gemma4:e2b
    """

    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        tags_raw = subreddit  # Pixiv adapter passes tags as the "subreddit" field
        illust_title = title

        prompt = (
            "You are extracting character and series names from Pixiv illustration tags.\n"
            "Pixiv tags often follow the pattern: CharacterName(SeriesName) or\n"
            "CharacterName（SeriesName）— both ASCII and Japanese/full-width bracket styles.\n"
            "Tags may be in Japanese, English, or a mix of both.\n\n"
            "Rules:\n"
            "- ONLY extract names that appear explicitly in the tags or title.\n"
            "- Translate Japanese names to their commonly known English names.\n"
            "  For example: '2B（ニーア オートマタ）' → name='2B', series='NieR:Automata'.\n"
            "  '胡桃(原神)' → name='Hu Tao', series='Genshin Impact'.\n"
            "  Only translate if you are confident. If not confident, omit entirely.\n"
            "- For tags in the format Name(Series) or Name（Series）, extract both name and series.\n"
            "- Ignore tags that are not character or series names (e.g. body part tags,\n"
            "  act descriptions, generic art style tags, view count tags like '1000users入り',\n"
            "  resolution tags, tool tags like 'Stable Diffusion').\n"
            "- Do not repeat entries already identified.\n"
            "- If a field has nothing confident to report, return empty list.\n"
            "- Respond ONLY with a JSON object. No explanation, no preamble, no markdown.\n\n"
            f"Already identified: {json.dumps(already_identified)}\n\n"
            f"Tags: {tags_raw}\n"
            f"Title: {illust_title}\n\n"
            "Response format:\n"
            '{"characters": [{"name": "English name", "series": "English series name or null"}], "artists": []}'
        )
        raw = _ollama_generate(settings.ollama_text_model, prompt)
        parsed = _parse_json(raw)

        raw_characters = list(parsed.get("characters") or [])
        characters = []
        for c in raw_characters:
            if isinstance(c, str):
                characters.append(CharacterHint(name=c.strip(), series=None))
            elif isinstance(c, dict):
                name = (c.get("name") or "").strip()
                series = (c.get("series") or "").strip() or None
                if name:
                    characters.append(CharacterHint(name=name, series=series))

        # Pixiv artist is always the uploader — extracted by the adapter, not the prompt
        return TextExtractionResult(
            characters=characters,
            artists=[],
            source_platform="Pixiv",
        )


# ── Legacy Ollama text providers (kept for backwards compat) ───────────────────

class OllamaTextExtractionProvider:
    """
    Legacy qwen2.5-based text extraction. Kept for backwards compatibility.
    Consider migrating to Gemma4TextExtractionProvider for better multilingual support.
    """

    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        prompt = (
            "You are a metadata extractor for anime, manga, and video game fanart.\n"
            "You will be given context signals about a piece of artwork — which may come\n"
            "from any platform (Reddit, Twitter, a fan site, etc). Extract ONLY metadata\n"
            "you are confident about. If you are not sure, omit it entirely — do not guess.\n\n"
            "Rules:\n"
            "- characters: ONLY extract if a character name is explicitly stated in the\n"
            "  title or flair/tags. Do not infer from the community/subreddit name alone.\n"
            "- artists: ONLY extract if there is an explicit credit in the title or flair\n"
            "  (e.g. 'by ArtistName', 'art by', '@handle', '[OC]' with a name).\n"
            "  Return the name only — strip any leading @ symbol.\n"
            "- source_platform: ONLY extract if a platform is explicitly named\n"
            "  (e.g. 'Pixiv', 'Twitter', 'ArtStation'). Do not infer from URLs alone.\n"
            "- If a field has nothing confident to report, return empty list or null.\n"
            "- Do not repeat entities already identified (listed below).\n"
            "- Respond ONLY in JSON. No explanation, no preamble, no markdown.\n\n"
            f"Already identified: {json.dumps(already_identified)}\n\n"
            f"Community/tags: {subreddit}\n"
            f"Title: {title}\n"
            f"Flair: {flair}\n\n"
            'Response format:\n'
            '{"characters": ["name1", "name2"], "artists": ["name1"], "source_platform": null}'
        )
        raw = _ollama_generate(settings.ollama_text_model, prompt)
        parsed = _parse_json(raw)

        raw_characters = list(parsed.get("characters") or [])
        characters = []
        for c in raw_characters:
            name = c if isinstance(c, str) else c.get("name", "")
            if name:
                characters.append(CharacterHint(name=name, series=None))

        raw_artists = [a if isinstance(a, str) else a.get("name", "") for a in list(parsed.get("artists") or [])]
        # Strip leading @ — Ollama sometimes returns "@handle" verbatim from the title
        artists = [a.lstrip("@").strip() for a in raw_artists if a]

        return TextExtractionResult(
            characters=characters,
            artists=artists,
            source_platform=parsed.get("source_platform"),
        )


class PixivOllamaTextExtractionProvider:
    """
    Legacy qwen2.5-based Pixiv text extraction. Kept for backwards compatibility.
    Consider migrating to Gemma4PixivTextExtractionProvider for better Japanese support.
    """

    def extract(self, subreddit: str, title: str, flair: str, already_identified: dict) -> TextExtractionResult:
        tags_raw = subreddit
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
        raw = _ollama_generate(settings.ollama_text_model, prompt)
        parsed = _parse_json(raw)

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


# ── WD Tagger v3 content rating ────────────────────────────────────────────────

class WDTaggerContentRatingProvider:
    """
    Anime-native content rating using WD SwinV2 Tagger v3.

    Trained on Danbooru images — far more accurate than general-purpose NSFW
    classifiers for anime/illustration content. Outputs a rating tag that maps
    directly to our SFW/Suggestive/NSFW scale:

        rating:general   → SFW
        rating:sensitive → Suggestive
        rating:questionable / rating:explicit → NSFW

    Uses the transformers-compatible HuggingFace conversion for easy loading.
    Model is loaded once and reused across all calls (no per-image reload).

    Install:
        pip install transformers timm pillow torch

    Set in .env:
        MEDIA_ARCHIVE_ENRICHMENT_CONTENT_PROVIDER=wd_tagger
        MEDIA_ARCHIVE_WD_TAGGER_MODEL=p1atdev/wd-swinv2-tagger-v3-hf
    """

    # Danbooru rating tag → our content rating value
    _RATING_MAP = {
        "rating:general": ("SFW", 0.95),
        "rating:sensitive": ("Suggestive", 0.85),
        "rating:questionable": ("NSFW", 0.90),
        "rating:explicit": ("NSFW", 0.98),
    }

    def __init__(self):
        from transformers import AutoImageProcessor, AutoModelForImageClassification
        import torch

        model_name = settings.wd_tagger_model
        self._processor = AutoImageProcessor.from_pretrained(
            model_name, trust_remote_code=True
        )
        self._model = AutoModelForImageClassification.from_pretrained(model_name)
        self._model.eval()
        self._torch = torch

    def classify(self, image_path: Path, subreddit_is_nsfw: bool) -> ContentRatingResult:
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        inputs = self._processor.preprocess(image, return_tensors="pt")

        with self._torch.no_grad():
            outputs = self._model(**inputs)
            logits = self._torch.sigmoid(outputs.logits[0])

        # Build label → score dict, filter to rating: tags only
        id2label = self._model.config.id2label
        scores = {
            id2label[i]: float(logit)
            for i, logit in enumerate(logits)
            if id2label[i].startswith("rating:")
        }

        if not scores:
            return ContentRatingResult(value=None, confidence=0.0, source="wd_tagger")

        # Pick highest scoring rating tag
        top_label = max(scores, key=lambda k: scores[k])
        top_score = scores[top_label]

        value, base_confidence = self._RATING_MAP.get(top_label, (None, 0.0))

        # If context says NSFW subreddit, bump borderline sensitive → NSFW
        if subreddit_is_nsfw and value == "Suggestive" and top_score >= 0.6:
            value = "NSFW"
            base_confidence = top_score

        confidence = min(top_score * base_confidence + (1 - base_confidence) * top_score, 1.0)
        return ContentRatingResult(value=value, confidence=round(confidence, 4), source="wd_tagger")


# ── Legacy HuggingFace content rating (kept for backwards compat) ──────────────

class HuggingFaceContentRatingProvider:
    """
    Legacy Falconsai NSFW classifier. Kept for backwards compatibility.
    Not recommended for anime/illustration content — use WDTaggerContentRatingProvider.
    """

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


# ── Gemma4 art type provider ───────────────────────────────────────────────────

class Gemma4ArtTypeProvider:
    """
    Art type classification using Gemma 4 E2B via Ollama.

    Classifies into: Artwork (drawn/illustrated), Cosplay (real photo of person
    in costume), AI Generated (synthetic AI image).

    Gemma 4 is significantly more reliable than llava-phi3 at distinguishing
    AI-generated art from hand-drawn illustration — the key hard case.

    Uses a low visual token budget (140) for fast inference on classification
    tasks that don't require fine-grained detail reading.

    Set in .env:
        MEDIA_ARCHIVE_ENRICHMENT_ART_TYPE_PROVIDER=gemma4
        MEDIA_ARCHIVE_OLLAMA_VISION_MODEL=gemma4:e2b
    """

    # Low token budget — classification doesn't need fine detail, just overall style
    _VISUAL_TOKEN_BUDGET = 140

    def classify(self, image_path: Path) -> ArtTypeResult:
        prompt = (
            "Classify this image into exactly one category:\n"
            "- Artwork: hand-drawn, painted, or digitally illustrated image (anime, manga, fanart, sketch)\n"
            "- Cosplay: real photograph of a person wearing a costume\n"
            "- AI Generated: image created by an AI image generator (Stable Diffusion, Midjourney, NovelAI, etc)\n\n"
            "AI Generated images often have: unnaturally perfect lighting, subtle anatomical errors,\n"
            "blurred backgrounds with dreamlike quality, or visible AI artifacts.\n"
            "Cosplay images contain real humans in costumes, not drawn characters.\n"
            "Artwork covers all hand-drawn or traditionally/digitally illustrated content.\n\n"
            "Respond ONLY with this JSON and nothing else:\n"
            "{\"art_type\": \"Artwork\", \"confidence\": 0.95}"
        )
        raw = _ollama_chat_vision(
            settings.ollama_vision_model,
            prompt,
            image_path,
            timeout=120,
        )
        parsed = _parse_json(raw)

        art_type = parsed.get("art_type")
        # Normalise to exact expected values
        if isinstance(art_type, str):
            art_type = art_type.strip()
            if art_type not in {"Artwork", "Cosplay", "AI Generated"}:
                # Try loose matching for common model variations
                lower = art_type.lower()
                if "cosplay" in lower:
                    art_type = "Cosplay"
                elif "ai" in lower or "generated" in lower or "artificial" in lower:
                    art_type = "AI Generated"
                else:
                    art_type = "Artwork"  # Default to Artwork for drawn content

        confidence = float(parsed.get("confidence", 0.0))
        return ArtTypeResult(
            value=art_type,
            confidence=confidence,
            source="gemma4_vision",
        )


# ── Legacy Ollama art type provider (kept for backwards compat) ────────────────

class OllamaArtTypeProvider:
    """
    Legacy llava-phi3 art type provider. Kept for backwards compatibility.
    Consider migrating to Gemma4ArtTypeProvider for better accuracy.
    """

    def classify(self, image_path: Path) -> ArtTypeResult:
        prompt = (
            "You are classifying a fanart image. Choose exactly one: "
            "Artwork (drawn/illustrated), Cosplay (real photo of person in costume), "
            "AI Generated (synthetic AI image). "
            "Respond with ONLY this JSON no other text: "
            "{\"art_type\": \"Artwork\", \"confidence\": 0.95}"
        )
        raw = _ollama_chat_vision(settings.ollama_vision_model, prompt, image_path)
        parsed = _parse_json(raw)
        return ArtTypeResult(
            value=parsed.get("art_type"),
            confidence=float(parsed.get("confidence", 0.0)),
            source="ollama_vision",
        )


# ── Provider factories ─────────────────────────────────────────────────────────

def get_text_provider(name: str) -> TextExtractionProvider:
    normalized = name.strip().lower()
    if normalized == "gemma4":
        return Gemma4TextExtractionProvider()
    if normalized == "gemma4_pixiv":
        return Gemma4PixivTextExtractionProvider()
    if normalized == "ollama":
        return OllamaTextExtractionProvider()
    if normalized == "ollama_pixiv":
        return PixivOllamaTextExtractionProvider()
    return NullTextExtractionProvider()


def get_content_provider(name: str) -> ContentRatingProvider:
    normalized = name.strip().lower()
    if normalized == "wd_tagger":
        return WDTaggerContentRatingProvider()
    if normalized in {"huggingface", "hf"}:
        return HuggingFaceContentRatingProvider()
    return NullContentRatingProvider()


def get_art_type_provider(name: str) -> ArtTypeProvider:
    normalized = name.strip().lower()
    if normalized == "gemma4":
        return Gemma4ArtTypeProvider()
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


def _check_wd_tagger() -> tuple[bool, str]:
    try:
        import transformers  # noqa: F401
        import timm  # noqa: F401
        return True, f"transformers + timm available (model: {settings.wd_tagger_model})"
    except ImportError as exc:
        return False, f"missing dependency: {exc} — run: pip install transformers timm"


def provider_health_snapshot() -> dict:
    snapshot = {
        "text_provider": settings.enrichment_text_provider,
        "content_provider": settings.enrichment_content_provider,
        "art_type_provider": settings.enrichment_art_type_provider,
        "checks": {},
    }

    text_name = settings.enrichment_text_provider.strip().lower()
    if text_name in {"gemma4", "gemma4_pixiv", "ollama", "ollama_pixiv"}:
        ok, detail = _check_ollama_model(settings.ollama_text_model)
        snapshot["checks"]["text"] = {"ok": ok, "detail": detail}
    else:
        snapshot["checks"]["text"] = {"ok": True, "detail": "disabled (provider=none)"}

    content_name = settings.enrichment_content_provider.strip().lower()
    if content_name == "wd_tagger":
        ok, detail = _check_wd_tagger()
        snapshot["checks"]["content_rating"] = {"ok": ok, "detail": detail}
    elif content_name in {"huggingface", "hf"}:
        try:
            import transformers  # noqa: F401
            snapshot["checks"]["content_rating"] = {"ok": True, "detail": "transformers import ok"}
        except Exception as exc:
            snapshot["checks"]["content_rating"] = {"ok": False, "detail": f"huggingface import failed: {exc}"}
    else:
        snapshot["checks"]["content_rating"] = {"ok": True, "detail": "disabled (provider=none)"}

    art_name = settings.enrichment_art_type_provider.strip().lower()
    if art_name in {"gemma4", "ollama"}:
        ok, detail = _check_ollama_model(settings.ollama_vision_model)
        snapshot["checks"]["art_type"] = {"ok": ok, "detail": detail}
    else:
        snapshot["checks"]["art_type"] = {"ok": True, "detail": "disabled (provider=none)"}

    snapshot["ready"] = all(bool(check["ok"]) for check in snapshot["checks"].values())
    return snapshot