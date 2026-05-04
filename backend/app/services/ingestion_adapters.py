import json
import subprocess
from pathlib import Path

from app.config import settings
from app.services.ingestion import IngestionAdapter, IngestionItem


class ManifestIngestionAdapter(IngestionAdapter):
    """
    Local test adapter.

    Reads a JSON manifest with entries:
    [
      {
        "file_path": "C:/path/to/file.jpg",
        "source_url": "https://reddit.com/...",
        "source_platform_url": "https://pixiv.net/...",
        "source_platform_name": "Reddit",
        "platform_context": {"subreddit": "...", "title": "...", "flair": "..."}
      }
    ]
    """

    def __init__(self, manifest_path: Path | None = None):
        self.manifest_path = manifest_path or settings.ingestion_manifest_path

    def fetch_items(self) -> list[IngestionItem]:
        if not self.manifest_path.exists():
            return []
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        items: list[IngestionItem] = []
        for entry in raw:
            items.append(
                IngestionItem(
                    file_path=Path(entry["file_path"]),
                    source_url=entry["source_url"],
                    source_platform_url=entry.get("source_platform_url"),
                    platform_context=entry.get("platform_context") or {},
                    source_platform_name=entry.get("source_platform_name") or settings.default_source_platform,
                )
            )
        return items


class GalleryDLIngestionAdapter(IngestionAdapter):
    """
    Gallery-DL adapter scaffold.

    This executes a configured gallery-dl command and then reads generated outputs from
    ingestion_work_dir/gallery_manifest.json in the same schema as ManifestIngestionAdapter.
    """

    MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".mp4", ".webm"}

    def fetch_items(self) -> list[IngestionItem]:
        settings.ingestion_work_dir.mkdir(parents=True, exist_ok=True)
        self._run_gallery_dl()
        return self._parse_gallery_outputs()

    def _run_gallery_dl(self) -> None:
        targets = [t.strip() for t in settings.gallery_dl_targets.split(",") if t.strip()]
        if not targets:
            raise ValueError("MEDIA_ARCHIVE_GALLERY_DL_TARGETS is required when ingestion adapter is gallery-dl.")

        extra_args = [a.strip() for a in settings.gallery_dl_extra_args.split(",") if a.strip()]
        command = ["gallery-dl", "--write-metadata", "--dest", str(settings.ingestion_work_dir), *extra_args, *targets]
        subprocess.run(command, check=True, cwd=settings.ingestion_work_dir)

    def _parse_gallery_outputs(self) -> list[IngestionItem]:
        items: list[IngestionItem] = []
        for metadata_path in settings.ingestion_work_dir.rglob("*.json"):
            metadata = self._read_json(metadata_path)
            if metadata is None:
                continue

            media_path = self._resolve_media_path(metadata_path, metadata)
            if media_path is None:
                continue

            source_url = self._resolve_source_url(metadata)
            if not source_url:
                # Preserve dedup semantics by requiring a source key.
                continue

            items.append(
                IngestionItem(
                    file_path=media_path,
                    source_url=source_url,
                    source_platform_url=self._resolve_source_platform_url(metadata),
                    platform_context=self._build_platform_context(metadata),
                    source_platform_name=self._resolve_source_platform_name(metadata),
                )
            )
        return items

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if isinstance(payload, dict):
            return payload
        return None

    def _resolve_media_path(self, metadata_path: Path, metadata: dict) -> Path | None:
        derived = metadata_path.with_suffix("")
        if derived.exists() and derived.suffix.lower() in self.MEDIA_SUFFIXES:
            return derived

        filename = metadata.get("filename")
        if isinstance(filename, str):
            candidate = Path(filename)
            if not candidate.is_absolute():
                candidate = metadata_path.parent / candidate
            if candidate.exists() and candidate.suffix.lower() in self.MEDIA_SUFFIXES:
                return candidate

        for sibling in metadata_path.parent.glob(f"{metadata_path.stem}*"):
            if sibling == metadata_path:
                continue
            if sibling.is_file() and sibling.suffix.lower() in self.MEDIA_SUFFIXES:
                return sibling
        return None

    @staticmethod
    def _resolve_source_url(metadata: dict) -> str | None:
        permalink = metadata.get("permalink")
        if isinstance(permalink, str) and permalink.strip():
            if permalink.startswith("http"):
                return permalink
            return f"https://reddit.com{permalink}"
        for key in ("post_url", "source_url", "url"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _resolve_source_platform_url(metadata: dict) -> str | None:
        for key in ("source_platform_url", "content_url", "referer"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _resolve_source_platform_name(metadata: dict) -> str:
        extractor = metadata.get("category") or metadata.get("extractor")
        if isinstance(extractor, str) and extractor.strip():
            return extractor.strip().title()
        return settings.default_source_platform

    @staticmethod
    def _build_platform_context(metadata: dict) -> dict:
        return {
            "subreddit": metadata.get("subreddit"),
            "title": metadata.get("title"),
            "flair": metadata.get("flair") or metadata.get("link_flair_text"),
        }

class TwitterIngestionAdapter(IngestionAdapter):
    """
    Twitter/X adapter for bookmarks and likes.

    Expects gallery-dl to have already downloaded media and metadata
    to ingestion_work_dir using this config:
    {
        "extractor": {
            "twitter": {
                "postprocessors": [{"name": "metadata", "event": "post", "filename": "{tweet_id}.json"}]
            }
        }
    }
    """

    MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".webm"}
    SKIP_SUFFIXES = {".part", ".json"}

    def __init__(self, targets: list[str] | None = None, work_dir: Path | None = None):
        self.targets = targets or [t.strip() for t in settings.gallery_dl_targets.split(",") if t.strip()]
        self.work_dir = work_dir or settings.ingestion_work_dir

    def fetch_items(self) -> list[IngestionItem]:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._run_gallery_dl()
        return self._parse_outputs()

    def _run_gallery_dl(self) -> None:
        if not self.targets:
            raise ValueError("No Twitter targets configured.")
        extra_args = [a.strip() for a in settings.gallery_dl_extra_args.split(",") if a.strip()]
        command = [
            "gallery-dl",
            "--dest", str(self.work_dir),
            "--range", f"1-{settings.ingestion_batch_size}",
            *extra_args,
            *self.targets
        ]
        subprocess.run(command, check=True)

    def _parse_outputs(self) -> list[IngestionItem]:
        items: list[IngestionItem] = []
        twitter_root = self.work_dir / "twitter"
        if not twitter_root.exists():
            return items

        for author_dir in twitter_root.iterdir():
            if not author_dir.is_dir():
                continue
            author_name = author_dir.name

            for json_path in author_dir.glob("*.json"):
                # skip stray info.json from old runs
                if json_path.stem == "info":
                    continue

                tweet_id = json_path.stem
                metadata = self._read_json(json_path)
                if not metadata:
                    continue

                # find all media files for this tweet
                media_files = sorted([
                    f for f in author_dir.iterdir()
                    if f.stem.startswith(f"{tweet_id}_")
                    and f.suffix.lower() in self.MEDIA_SUFFIXES
                    and not f.name.endswith(".part")
                ])

                for media_file in media_files:
                    # use tweet_id + filename as unique source_url to handle multi-image
                    source_url = f"https://x.com/{author_name}/status/{tweet_id}/{media_file.name}"
                    items.append(IngestionItem(
                        file_path=media_file,
                        source_url=source_url,
                        source_platform_url=f"https://x.com/{author_name}/status/{tweet_id}",
                        platform_context={
                            "tweet_id": tweet_id,
                            "author": author_name,
                            "content": metadata.get("content", ""),
                            "sensitive": metadata.get("sensitive", False),
                            "author_url": metadata.get("author", {}).get("url", ""),
                        },
                        source_platform_name="Twitter",
                    ))
        return items

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

def get_ingestion_adapter(adapter_name: str) -> IngestionAdapter:
    normalized = adapter_name.strip().lower()
    if normalized == "gallery-dl":
        return GalleryDLIngestionAdapter()
    if normalized == "twitter":
        return TwitterIngestionAdapter()
    return ManifestIngestionAdapter()