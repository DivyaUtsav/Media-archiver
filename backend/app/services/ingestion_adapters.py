import hashlib
import http.cookiejar
import json
import logging
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services.ingestion import IngestionAdapter, IngestionItem, is_duplicate_source

logger = logging.getLogger(__name__)


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
                            "author_is_artist": True,
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


class PixivIngestionAdapter:
    """
    Pixiv adapter supporting bookmarks and likes.

    Runs gallery-dl against configured Pixiv targets, then parses
    downloaded files and per-illustration metadata JSON files.
    Uses database dedup to stop after batch_size new items.

    Requires gallery-dl config at %APPDATA%/gallery-dl/config.json with:
    {
        "extractor": {
            "pixiv": {
                "username": "...",
                "password": "...",
                "postprocessors": [{"name": "metadata", "event": "post", "filename": "{id}.json"}]
            }
        }
    }
    """

    MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".zip", ".mp4", ".webm"}

    def __init__(self, targets: list[str] | None = None, work_dir: Path | None = None):
        self.targets = targets or [t.strip() for t in settings.gallery_dl_targets.split(",") if t.strip()]
        self.work_dir = work_dir or settings.ingestion_work_dir

    def fetch_items(self, db: Session, batch_size: int) -> list[IngestionItem]:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._run_gallery_dl(batch_size=batch_size)
        return self._parse_outputs(db=db, batch_size=batch_size)

    def _run_gallery_dl(self, batch_size: int) -> None:
        if not self.targets:
            raise ValueError("No Pixiv targets configured. Set MEDIA_ARCHIVE_GALLERY_DL_TARGETS.")

        cmd = ["gallery-dl", "--dest", str(self.work_dir), "--range", f"1-{batch_size}"]

        if settings.gallery_dl_cookies_file:
            cmd += ["--cookies", settings.gallery_dl_cookies_file]

        extra_args = [a.strip() for a in settings.gallery_dl_extra_args.split(",") if a.strip()]
        if extra_args:
            cmd += extra_args

        cmd += self.targets
        subprocess.run(cmd, check=True)

    def _parse_outputs(self, db: Session, batch_size: int) -> list[IngestionItem]:
        items: list[IngestionItem] = []

        # Pixiv structure: work_dir/pixiv/{subcategory}/{user_id} {username}/
        pixiv_root = self.work_dir / "pixiv"
        if not pixiv_root.exists():
            return items

        for subcategory_dir in pixiv_root.iterdir():
            if not subcategory_dir.is_dir():
                continue
            for user_dir in subcategory_dir.iterdir():
                if not user_dir.is_dir():
                    continue
                if len(items) >= batch_size:
                    break

                for json_path in sorted(user_dir.glob("*.json"), reverse=True):
                    if json_path.stem == "info":
                        continue
                    if len(items) >= batch_size:
                        break

                    illust_id = json_path.stem
                    metadata = self._read_json(json_path)
                    if not metadata:
                        continue

                    artist_name = (metadata.get("user") or {}).get("name", "")
                    artist_account = (metadata.get("user") or {}).get("account", "")

                    # Find all media files for this illustration
                    media_files = sorted([
                        f for f in user_dir.iterdir()
                        if f.stem.startswith(f"{illust_id}_")
                        and f.suffix.lower() in self.MEDIA_SUFFIXES
                        and not f.name.endswith(".part")
                    ])

                    for media_file in media_files:
                        if len(items) >= batch_size:
                            break

                        source_url = f"https://www.pixiv.net/artworks/{illust_id}/{media_file.name}"
                        if is_duplicate_source(db, source_url):
                            continue

                        # Extract tags as list of strings
                        raw_tags = metadata.get("tags") or []
                        tags = [t if isinstance(t, str) else t.get("name", "") for t in raw_tags]
                        tags = [t for t in tags if t]

                        items.append(IngestionItem(
                            file_path=media_file,
                            source_url=source_url,
                            source_platform_url=f"https://www.pixiv.net/artworks/{illust_id}",
                            platform_context={
                                "illust_id": illust_id,
                                "title": metadata.get("title", ""),
                                "author": artist_name,
                                "author_is_artist": True,
                                "author_account": artist_account,
                                "tags": tags,
                                "type": metadata.get("type", "illust"),
                                "x_restrict": metadata.get("x_restrict", 0),
                                "sanity_level": metadata.get("sanity_level", 2),
                                "illust_ai_type": metadata.get("illust_ai_type", 0),
                                "page_count": metadata.get("page_count", 1),
                                "series": metadata.get("series"),
                            },
                            source_platform_name="Pixiv",
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


# ─────────────────────────────────────────────────────────────────────────────
# Reddit
# ─────────────────────────────────────────────────────────────────────────────

_REDDIT_SAVED_URL = "https://www.reddit.com/user/{username}/saved.json"

_REDDIT_MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_REDDIT_IMAGE_HOSTS = {"i.redd.it", "i.imgur.com", "preview.redd.it"}

# Spacing between image downloads
_REDDIT_DOWNLOAD_DELAY = 2.0

_REDDIT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
}


class RedditIngestionAdapter:
    """
    Ingests image posts from your Reddit saved posts list using browser cookie auth.

    No OAuth or API approval required — uses your own Reddit session cookies
    exported from a browser. Paginates through your saved posts (Reddit caps
    this at 1000 total, 100 per page) and downloads image posts it hasn't
    seen before.

    Required .env:
        MEDIA_ARCHIVE_REDDIT_USERNAME=your_reddit_username
        MEDIA_ARCHIVE_REDDIT_COOKIES_FILE=C:/path/to/reddit_cookies.txt

    Optional .env:
        MEDIA_ARCHIVE_REDDIT_MIN_SCORE=0   # skip posts below this upvote count

    Export cookies with "Get cookies.txt LOCALLY" Chrome/Firefox extension
    while logged into reddit.com. Re-export every few weeks when they expire.
    """

    def __init__(
        self,
        username: str | None = None,
        cookies_file: Path | None = None,
        work_dir: Path | None = None,
        min_score: int | None = None,
    ):
        self.username = username if username is not None else settings.reddit_username
        self.cookies_file = Path(
            cookies_file or settings.reddit_cookies_file or ""
        ) if (cookies_file or settings.reddit_cookies_file) else None
        self.work_dir = work_dir or settings.ingestion_work_dir
        self.min_score = min_score if min_score is not None else settings.reddit_min_score

    # ── Public interface ────────────────────────────────────────────────────────

    def fetch_items(self, db: Session, batch_size: int) -> list[IngestionItem]:
        if not self.username:
            raise ValueError(
                "Reddit username not configured. Set MEDIA_ARCHIVE_REDDIT_USERNAME."
            )
        if not self.cookies_file or not self.cookies_file.exists():
            raise ValueError(
                f"Reddit cookies file not found: {self.cookies_file!r}. "
                "Export your Reddit session cookies as cookies.txt and set "
                "MEDIA_ARCHIVE_REDDIT_COOKIES_FILE."
            )

        self.work_dir.mkdir(parents=True, exist_ok=True)
        reddit_work = self.work_dir / "reddit" / "saved"
        reddit_work.mkdir(parents=True, exist_ok=True)

        client = self._build_client()
        items: list[IngestionItem] = []

        try:
            after: str | None = None

            while len(items) < batch_size:
                posts, after = self._fetch_saved_page(client, after)
                if not posts:
                    break

                for post in posts:
                    if len(items) >= batch_size:
                        break

                    # Saved list includes comments (kind=t1) — skip them,
                    # we only want link posts (kind=t3).
                    if post.get("_kind") != "t3":
                        continue

                    image_url = self._extract_image_url(post)
                    if not image_url:
                        continue

                    source_url = self._post_source_url(post)
                    if not source_url:
                        continue

                    if is_duplicate_source(db, source_url):
                        logger.debug("Duplicate, skipping: %s", source_url)
                        continue

                    score = int(post.get("score") or 0)
                    if score < self.min_score:
                        logger.debug(
                            "Score %d below minimum %d, skipping: %s",
                            score, self.min_score, source_url,
                        )
                        continue

                    try:
                        media_path = self._download_image(client, image_url, reddit_work)
                    except Exception as exc:
                        logger.warning("Failed to download %s: %s", image_url, exc)
                        continue

                    if media_path is None:
                        continue

                    items.append(IngestionItem(
                        file_path=media_path,
                        source_url=source_url,
                        source_platform_url=image_url,
                        platform_context={
                            "subreddit": post.get("subreddit", ""),
                            "title": post.get("title", ""),
                            "flair": post.get("link_flair_text") or "",
                            "author": post.get("author", ""),
                            "score": score,
                            "post_id": post.get("id", ""),
                            "nsfw": bool(post.get("over_18", False)),
                        },
                        source_platform_name="Reddit",
                        original_file_path=media_path,
                    ))
                    time.sleep(_REDDIT_DOWNLOAD_DELAY)

                if after is None:
                    break  # Reddit returned no cursor — end of saved list

        finally:
            client.close()

        return items

    # ── HTTP client ─────────────────────────────────────────────────────────────

    def _build_client(self) -> httpx.Client:
        jar = http.cookiejar.MozillaCookieJar()
        jar.load(str(self.cookies_file), ignore_discard=True, ignore_expires=True)
        cookies = httpx.Cookies()
        for cookie in jar:
            cookies.set(cookie.name, cookie.value, domain=cookie.domain)
        return httpx.Client(
            headers=_REDDIT_HEADERS,
            cookies=cookies,
            follow_redirects=True,
            timeout=30.0,
        )

    # ── Saved posts pagination ──────────────────────────────────────────────────

    def _fetch_saved_page(
        self, client: httpx.Client, after: str | None
    ) -> tuple[list[dict], str | None]:
        """
        Fetch one page of saved posts (max 100 per request).
        Returns (posts, next_after_cursor).
        next_after_cursor is None when there are no more pages.
        """
        url = _REDDIT_SAVED_URL.format(username=self.username)
        params: dict = {"limit": 100, "raw_json": 1}
        if after:
            params["after"] = after

        try:
            resp = client.get(url, params=params)
        except httpx.RequestError as exc:
            logger.warning("Request error fetching saved posts: %s", exc)
            return [], None

        if resp.status_code == 403:
            raise PermissionError(
                "Reddit returned 403 fetching saved posts — cookies may be expired "
                "or the username is wrong. Re-export cookies from your browser and try again."
            )
        if resp.status_code != 200:
            logger.warning("Saved posts endpoint returned HTTP %d", resp.status_code)
            return [], None

        try:
            data = resp.json()
        except Exception:
            logger.warning("Failed to parse saved posts JSON response")
            return [], None

        listing = data.get("data") or {}
        children = listing.get("children") or []
        next_after = listing.get("after")  # None when we've reached the last page

        # Stash the `kind` field (t3=link post, t1=comment) onto each data dict
        posts = []
        for child in children:
            post_data = child.get("data") or {}
            post_data["_kind"] = child.get("kind", "")
            posts.append(post_data)

        return posts, next_after

    # ── Image URL extraction ────────────────────────────────────────────────────

    @staticmethod
    def _extract_image_url(post: dict) -> str | None:
        url = post.get("url", "")
        if not url:
            return None

        parsed = urlparse(url)
        host = parsed.netloc.lower().lstrip("www.")

        # Direct i.redd.it links — always an image
        if host == "i.redd.it":
            return url

        # preview.redd.it — valid image, unescape HTML entities
        if host == "preview.redd.it":
            return url.replace("&amp;", "&")

        # imgur direct image links only (not imgur gallery pages)
        if host == "i.imgur.com" and any(
            url.lower().endswith(ext) for ext in _REDDIT_MEDIA_SUFFIXES
        ):
            return url

        # Fall back to Reddit's own preview thumbnail — covers gallery posts,
        # external links with previews, and most other image-bearing posts
        preview = post.get("preview") or {}
        images = preview.get("images") or []
        if images:
            source = (images[0].get("source") or {})
            preview_url = source.get("url", "")
            if preview_url:
                return preview_url.replace("&amp;", "&")

        return None

    # ── Image downloading ───────────────────────────────────────────────────────

    @staticmethod
    def _download_image(
        client: httpx.Client,
        image_url: str,
        work_dir: Path,
    ) -> Path | None:
        parsed = urlparse(image_url)
        url_filename = Path(parsed.path).name

        if "." in url_filename:
            parts = url_filename.rsplit(".", 1)
            stem = parts[0]
            ext = "." + parts[1].split("?")[0]
        else:
            stem = hashlib.md5(image_url.encode()).hexdigest()[:12]
            ext = ".jpg"

        if ext.lower() not in _REDDIT_MEDIA_SUFFIXES:
            ext = ".jpg"

        dest = work_dir / f"{stem}{ext}"

        # Idempotent — skip re-download if file already exists from a prior run
        if dest.exists():
            return dest

        try:
            resp = client.get(image_url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP %d downloading %s", exc.response.status_code, image_url)
            return None

        content_type = resp.headers.get("content-type", "")
        if "text" in content_type or "html" in content_type:
            logger.warning(
                "Non-image content-type %r for %s — skipping", content_type, image_url
            )
            return None

        dest.write_bytes(resp.content)
        logger.debug("Downloaded %s → %s", image_url, dest)
        return dest

    # ── Source URL construction ─────────────────────────────────────────────────

    @staticmethod
    def _post_source_url(post: dict) -> str | None:
        permalink = post.get("permalink", "")
        if not permalink:
            return None
        if permalink.startswith("http"):
            return permalink
        return f"https://www.reddit.com{permalink}"


# ─────────────────────────────────────────────────────────────────────────────
# Reddit CSV backlog adapter
# ─────────────────────────────────────────────────────────────────────────────

class RedditCSVIngestionAdapter:
    """
    Ingests artwork from a Reddit data-export CSV (saved_posts.csv).

    Designed for the one-time backlog import of your full Reddit saved posts
    history, which the live RedditIngestionAdapter can't reach (Reddit caps
    the API at 1000 saved posts, but your data export has all 2600+).

    The CSV must have at minimum two columns: `id` and `permalink`.
    This matches the format produced by Reddit's own GDPR data export.

    Handles all real-world failure modes gracefully:
      - Deleted posts (permalink contains "deleted_by_user", or post 404s)
      - Text/link posts with no image (skipped, not errored)
      - Unavailable images (i.redd.it 404, CDN errors — skipped)
      - Already-ingested posts (dedup via source_url)
      - Rate limiting (2s delay between image downloads)

    Progress is tracked in a sidecar JSON file next to the CSV so runs can
    be interrupted and resumed without re-processing already-seen posts.

    Required .env:
        MEDIA_ARCHIVE_REDDIT_COOKIES_FILE=C:/path/to/reddit_cookies.txt

    Optional .env:
        MEDIA_ARCHIVE_REDDIT_CSV_PATH=C:/path/to/saved_posts.csv
          (defaults to saved_posts.csv next to the CSV or settings value)

    Usage via script:
        python scripts/run_reddit_csv_import.py
        python scripts/run_reddit_csv_import.py --batch-size 50
        python scripts/run_reddit_csv_import.py --reset-progress
    """

    # Seconds to wait between individual post fetches (not just downloads)
    # — keeps total request rate well under Reddit's tolerance
    _POST_FETCH_DELAY = 1.5

    def __init__(
        self,
        csv_path: Path | None = None,
        cookies_file: Path | None = None,
        work_dir: Path | None = None,
    ):
        self.csv_path = Path(
            csv_path or settings.reddit_csv_path or "saved_posts.csv"
        )
        self.cookies_file = Path(
            cookies_file or settings.reddit_cookies_file or ""
        ) if (cookies_file or settings.reddit_cookies_file) else None
        self.work_dir = work_dir or settings.ingestion_work_dir

        # Progress file sits next to the CSV: saved_posts.progress.json
        self.progress_file = self.csv_path.with_suffix(".progress.json")

    # ── Public interface ────────────────────────────────────────────────────────

    def fetch_items(self, db: Session, batch_size: int) -> list[IngestionItem]:
        if not self.csv_path.exists():
            raise FileNotFoundError(
                f"Reddit saved posts CSV not found: {self.csv_path}. "
                "Request your data from reddit.com/settings/data-request."
            )
        if not self.cookies_file or not self.cookies_file.exists():
            raise ValueError(
                f"Reddit cookies file not found: {self.cookies_file!r}. "
                "Set MEDIA_ARCHIVE_REDDIT_COOKIES_FILE."
            )

        self.work_dir.mkdir(parents=True, exist_ok=True)
        reddit_work = self.work_dir / "reddit" / "csv_import"
        reddit_work.mkdir(parents=True, exist_ok=True)

        rows = self._load_csv()
        progress = self._load_progress()
        client = self._build_client()
        items: list[IngestionItem] = []

        stats = {"skipped_deleted": 0, "skipped_no_image": 0, "skipped_duplicate": 0, "failed_download": 0}

        try:
            for row in rows:
                if len(items) >= batch_size:
                    break

                post_id = row.get("id", "").strip()
                permalink = row.get("permalink", "").strip()

                if not post_id or not permalink:
                    continue

                # Skip posts already processed in a previous run
                if post_id in progress["seen"]:
                    continue

                # Mark as seen immediately — even if we skip/fail, we don't
                # want to retry a deleted or image-less post on every run
                progress["seen"].add(post_id)

                # Fast-path: deleted posts are flagged in the permalink itself
                if "deleted_by_user" in permalink or "removed_by_moderator" in permalink:
                    stats["skipped_deleted"] += 1
                    logger.debug("Deleted post, skipping: %s", permalink)
                    continue

                # Canonical source URL for dedup — the permalink is the post page
                source_url = permalink if permalink.startswith("http") else f"https://www.reddit.com{permalink}"

                if is_duplicate_source(db, source_url):
                    stats["skipped_duplicate"] += 1
                    logger.debug("Duplicate, skipping: %s", source_url)
                    continue

                # Fetch the post JSON to get image URL and metadata
                time.sleep(self._POST_FETCH_DELAY)
                post_data = self._fetch_post(client, post_id)

                if post_data is None:
                    # 404, deleted, or private — not worth retrying
                    stats["skipped_deleted"] += 1
                    logger.debug("Post unavailable: %s", source_url)
                    continue

                image_url = RedditIngestionAdapter._extract_image_url(post_data)
                if not image_url:
                    stats["skipped_no_image"] += 1
                    logger.debug("No image in post: %s", source_url)
                    continue

                try:
                    media_path = RedditIngestionAdapter._download_image(
                        client, image_url, reddit_work
                    )
                except Exception as exc:
                    stats["failed_download"] += 1
                    logger.warning("Download failed for %s: %s", image_url, exc)
                    continue

                if media_path is None:
                    stats["failed_download"] += 1
                    continue

                items.append(IngestionItem(
                    file_path=media_path,
                    source_url=source_url,
                    source_platform_url=image_url,
                    platform_context={
                        "subreddit": post_data.get("subreddit", ""),
                        "title": post_data.get("title", ""),
                        "flair": post_data.get("link_flair_text") or "",
                        "author": post_data.get("author", ""),
                        "score": int(post_data.get("score") or 0),
                        "post_id": post_id,
                        "nsfw": bool(post_data.get("over_18", False)),
                    },
                    source_platform_name="Reddit",
                    original_file_path=media_path,
                ))

        finally:
            # Always save progress — even if we error mid-batch, we don't
            # reprocess posts we already visited
            self._save_progress(progress)
            client.close()

        logger.info(
            "CSV batch complete — ingested=%d, skipped_deleted=%d, "
            "skipped_no_image=%d, skipped_duplicate=%d, failed_download=%d",
            len(items), stats["skipped_deleted"], stats["skipped_no_image"],
            stats["skipped_duplicate"], stats["failed_download"],
        )
        return items

    def reset_progress(self) -> None:
        """Delete the progress file so the next run starts from the beginning."""
        if self.progress_file.exists():
            self.progress_file.unlink()
            logger.info("Progress reset — next run will process all CSV rows.")

    def progress_summary(self) -> dict:
        """Return a summary of how far through the CSV we are."""
        rows = self._load_csv()
        progress = self._load_progress()
        total = len(rows)
        seen = len(progress["seen"])
        return {"total": total, "seen": seen, "remaining": total - seen}

    # ── CSV loading ─────────────────────────────────────────────────────────────

    def _load_csv(self) -> list[dict]:
        import csv
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    # ── Progress tracking ───────────────────────────────────────────────────────

    def _load_progress(self) -> dict:
        if self.progress_file.exists():
            try:
                raw = json.loads(self.progress_file.read_text(encoding="utf-8"))
                return {"seen": set(raw.get("seen", []))}
            except Exception:
                pass
        return {"seen": set()}

    def _save_progress(self, progress: dict) -> None:
        payload = {"seen": list(progress["seen"])}
        self.progress_file.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    # ── HTTP client ─────────────────────────────────────────────────────────────

    def _build_client(self) -> httpx.Client:
        jar = http.cookiejar.MozillaCookieJar()
        jar.load(str(self.cookies_file), ignore_discard=True, ignore_expires=True)
        cookies = httpx.Cookies()
        for cookie in jar:
            cookies.set(cookie.name, cookie.value, domain=cookie.domain)
        return httpx.Client(
            headers=_REDDIT_HEADERS,
            cookies=cookies,
            follow_redirects=True,
            timeout=30.0,
        )

    # ── Post fetching ───────────────────────────────────────────────────────────

    def _fetch_post(self, client: httpx.Client, post_id: str) -> dict | None:
        """
        Fetch a single post by ID using the .json endpoint.
        Returns the post data dict, or None if unavailable/deleted/not an image post.
        """
        # Reddit's per-post JSON: /comments/{id}.json returns a 2-element listing
        url = f"https://www.reddit.com/comments/{post_id}.json"
        try:
            resp = client.get(url, params={"raw_json": 1})
        except httpx.RequestError as exc:
            logger.debug("Request error fetching post %s: %s", post_id, exc)
            return None

        if resp.status_code in (404, 403, 410):
            logger.debug("Post %s returned HTTP %d", post_id, resp.status_code)
            return None
        if resp.status_code != 200:
            logger.debug("Post %s returned unexpected HTTP %d", post_id, resp.status_code)
            return None

        try:
            data = resp.json()
        except Exception:
            return None

        # Response is [post_listing, comments_listing]
        # post_listing.data.children[0].data is the post itself
        try:
            post = data[0]["data"]["children"][0]["data"]
        except (IndexError, KeyError, TypeError):
            return None

        # Deleted posts come back with author "[deleted]" and selftext "[removed]"
        if post.get("author") == "[deleted]" and post.get("selftext") in ("[removed]", "[deleted]"):
            logger.debug("Post %s is deleted", post_id)
            return None

        return post


# ─────────────────────────────────────────────────────────────────────────────

def get_ingestion_adapter(adapter_name: str) -> IngestionAdapter:
    normalized = adapter_name.strip().lower()
    if normalized == "gallery-dl":
        return GalleryDLIngestionAdapter()
    if normalized == "twitter":
        return TwitterIngestionAdapter()
    if normalized == "pixiv":
        return PixivIngestionAdapter()
    if normalized == "reddit":
        return RedditIngestionAdapter()
    if normalized == "reddit-csv":
        return RedditCSVIngestionAdapter()
    return ManifestIngestionAdapter()