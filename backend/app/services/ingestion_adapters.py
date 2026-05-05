import json
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.services.ingestion import IngestionAdapter, IngestionItem, is_duplicate_source


class ManifestIngestionAdapter:
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

    def fetch_items(self, db: Session, batch_size: int) -> list[IngestionItem]:
        if not self.manifest_path.exists():
            return []
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        items: list[IngestionItem] = []
        for entry in raw:
            item = IngestionItem(
                file_path=Path(entry["file_path"]),
                source_url=entry["source_url"],
                source_platform_url=entry.get("source_platform_url"),
                platform_context=entry.get("platform_context") or {},
                source_platform_name=entry.get("source_platform_name") or settings.default_source_platform,
            )
            if is_duplicate_source(db, item.source_url):
                continue
            items.append(item)
        return items


class GalleryDLIngestionAdapter:
    """
    Generic Gallery-DL adapter scaffold for future platform support.

    Executes a configured gallery-dl command and reads generated outputs
    from ingestion_work_dir. Intended as a base for platform-specific adapters.
    """

    MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".mp4", ".webm"}

    def fetch_items(self, db: Session, batch_size: int) -> list[IngestionItem]:
        settings.ingestion_work_dir.mkdir(parents=True, exist_ok=True)
        self._run_gallery_dl()
        return self._parse_gallery_outputs(db=db, batch_size=batch_size)

    def _run_gallery_dl(self) -> None:
        targets = [t.strip() for t in settings.gallery_dl_targets.split(",") if t.strip()]
        if not targets:
            raise ValueError("MEDIA_ARCHIVE_GALLERY_DL_TARGETS is required when ingestion adapter is gallery-dl.")

        extra_args = [a.strip() for a in settings.gallery_dl_extra_args.split(",") if a.strip()]
        command = ["gallery-dl", "--write-metadata", "--dest", str(settings.ingestion_work_dir), *extra_args, *targets]
        subprocess.run(command, check=True, cwd=settings.ingestion_work_dir)

    def _parse_gallery_outputs(self, db: Session, batch_size: int) -> list[IngestionItem]:
        items: list[IngestionItem] = []
        for metadata_path in settings.ingestion_work_dir.rglob("*.json"):
            if len(items) >= batch_size:
                break
            metadata = self._read_json(metadata_path)
            if metadata is None:
                continue

            media_path = self._resolve_media_path(metadata_path, metadata)
            if media_path is None:
                continue

            source_url = self._resolve_source_url(metadata)
            if not source_url:
                continue

            if is_duplicate_source(db, source_url):
                continue

            items.append(
                IngestionItem(
                    file_path=media_path,
                    source_url=source_url,
                    source_platform_url=self._resolve_source_platform_url(metadata),
                    platform_context=self._build_platform_context(metadata),
                    source_platform_name=self._resolve_source_platform_name(metadata),
                    original_file_path=media_path,
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
                candidate = metadata_path.parent / filename
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
            "author": metadata.get("author"),
        }


class TwitterIngestionAdapter:
    """
    Twitter/X adapter supporting bookmarks and likes.

    Runs gallery-dl against configured targets (bookmarks and/or likes URLs),
    then parses the downloaded files and metadata. Uses database dedup to stop
    after batch_size new items — does not rely on file presence in ingestion_work.

    Requires gallery-dl config at %APPDATA%/gallery-dl/config.json with:
    {
        "extractor": {
            "twitter": {
                "cookies": "<path to cookies.txt>",
                "postprocessors": [{"name": "metadata", "event": "post", "filename": "{tweet_id}.json"}]
            }
        }
    }
    """

    MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".webm"}

    def __init__(self, targets: list[str] | None = None, work_dir: Path | None = None):
        self.targets = targets or [t.strip() for t in settings.gallery_dl_targets.split(",") if t.strip()]
        self.work_dir = work_dir or settings.ingestion_work_dir

    def fetch_items(self, db: Session, batch_size: int) -> list[IngestionItem]:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._run_gallery_dl(batch_size=batch_size)
        return self._parse_outputs(db=db, batch_size=batch_size)

    def _run_gallery_dl(self, batch_size: int) -> None:
        if not self.targets:
            raise ValueError("No Twitter targets configured. Set MEDIA_ARCHIVE_GALLERY_DL_TARGETS.")

        cmd = ["gallery-dl", "--dest", str(self.work_dir), "--range", f"1-{batch_size}"]

        # Attach cookies file if configured
        if settings.gallery_dl_cookies_file:
            cmd += ["--cookies", settings.gallery_dl_cookies_file]

        extra_args = [a.strip() for a in settings.gallery_dl_extra_args.split(",") if a.strip()]
        if extra_args:
            cmd += extra_args

        cmd += self.targets
        subprocess.run(cmd, check=True)

    def _parse_outputs(self, db: Session, batch_size: int) -> list[IngestionItem]:
        items: list[IngestionItem] = []
        twitter_root = self.work_dir / "twitter"
        if not twitter_root.exists():
            return items

        for author_dir in sorted(twitter_root.iterdir()):
            if not author_dir.is_dir():
                continue
            if len(items) >= batch_size:
                break

            for json_path in sorted(author_dir.glob("*.json"), reverse=True):
                # Skip stray info.json files from old runs
                if json_path.stem == "info":
                    continue
                if len(items) >= batch_size:
                    break

                tweet_id = json_path.stem
                metadata = self._read_json(json_path)
                if not metadata:
                    continue

                # Always get author from metadata, not folder name.
                # Folder name is the liker's username for liked tweets — not the real author.
                real_author = (metadata.get("author") or {}).get("name") or author_dir.name
                author_url = (metadata.get("author") or {}).get("url", "")

                media_files = sorted([
                    f for f in author_dir.iterdir()
                    if f.stem.startswith(f"{tweet_id}_")
                    and f.suffix.lower() in self.MEDIA_SUFFIXES
                    and not f.name.endswith(".part")
                ])

                for media_file in media_files:
                    if len(items) >= batch_size:
                        break

                    # Per-image dedup key — handles multi-image tweets as separate artworks
                    source_url = f"https://x.com/{real_author}/status/{tweet_id}/{media_file.name}"
                    if is_duplicate_source(db, source_url):
                        continue

                    items.append(IngestionItem(
                        file_path=media_file,
                        source_url=source_url,
                        source_platform_url=f"https://x.com/{real_author}/status/{tweet_id}",
                        platform_context={
                            "tweet_id": tweet_id,
                            "author": real_author,
                            "content": metadata.get("content", ""),
                            "sensitive": metadata.get("sensitive", False),
                            "author_url": author_url,
                        },
                        source_platform_name="Twitter",
                        original_file_path=media_file,
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