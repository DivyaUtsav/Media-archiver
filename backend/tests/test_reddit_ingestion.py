"""
Tests for RedditIngestionAdapter (saved posts).

Run from the backend/ directory:
    pytest tests/test_reddit_ingestion.py -v
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.ingestion_adapters import RedditIngestionAdapter


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def cookies_file(tmp_path: Path) -> Path:
    """Minimal valid Netscape cookies.txt file."""
    f = tmp_path / "cookies.txt"
    f.write_text(
        "# Netscape HTTP Cookie File\n"
        ".reddit.com\tTRUE\t/\tTRUE\t9999999999\treddit_session\tfake_session_value\n",
        encoding="utf-8",
    )
    return f


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    return tmp_path / "ingestion_work"


@pytest.fixture
def db() -> MagicMock:
    db = MagicMock()
    # is_duplicate_source calls db.scalar — return None (not a duplicate) by default
    db.scalar.return_value = None
    return db


def make_saved_post(
    post_id: str = "abc123",
    subreddit: str = "NieRAutomatafanart",
    title: str = "2B fanart",
    author: str = "artist_user",
    url: str = "https://i.redd.it/abc123.jpg",
    permalink: str = "/r/NieRAutomatafanart/comments/abc123/2b_fanart/",
    flair: str = "Fanart",
    score: int = 100,
    over_18: bool = False,
    kind: str = "t3",
) -> dict:
    """Build a post dict as returned by _fetch_saved_page (with _kind injected)."""
    return {
        "_kind": kind,
        "id": post_id,
        "title": title,
        "author": author,
        "subreddit": subreddit,
        "url": url,
        "permalink": permalink,
        "link_flair_text": flair,
        "score": score,
        "over_18": over_18,
        "domain": "i.redd.it",
        "post_hint": "image",
        "preview": None,
    }


# ── _extract_image_url ─────────────────────────────────────────────────────────

class TestExtractImageUrl:
    def test_direct_i_redd_it(self):
        post = make_saved_post(url="https://i.redd.it/xkcd1234.jpg")
        assert RedditIngestionAdapter._extract_image_url(post) == "https://i.redd.it/xkcd1234.jpg"

    def test_i_redd_it_no_extension(self):
        # i.redd.it links don't always have an extension
        post = make_saved_post(url="https://i.redd.it/xkcd1234")
        assert RedditIngestionAdapter._extract_image_url(post) == "https://i.redd.it/xkcd1234"

    def test_preview_redd_it_url(self):
        post = make_saved_post(url="https://preview.redd.it/abc.jpg?auto=webp&s=xyz")
        result = RedditIngestionAdapter._extract_image_url(post)
        assert result == "https://preview.redd.it/abc.jpg?auto=webp&s=xyz"

    def test_preview_redd_it_unescapes_ampersand(self):
        post = make_saved_post(url="https://preview.redd.it/abc.jpg?auto=webp&amp;s=xyz")
        result = RedditIngestionAdapter._extract_image_url(post)
        assert "&amp;" not in result
        assert "&s=xyz" in result

    def test_imgur_direct_image(self):
        post = make_saved_post(url="https://i.imgur.com/abcdef.png")
        assert RedditIngestionAdapter._extract_image_url(post) == "https://i.imgur.com/abcdef.png"

    def test_imgur_page_link_falls_back_to_preview(self):
        # imgur.com/abcdef (no extension) — not a direct image, uses preview fallback
        post = make_saved_post(url="https://imgur.com/abcdef")
        post["preview"] = {
            "images": [{"source": {"url": "https://preview.redd.it/fallback.jpg?auto=webp&amp;s=xyz"}}]
        }
        result = RedditIngestionAdapter._extract_image_url(post)
        assert result == "https://preview.redd.it/fallback.jpg?auto=webp&s=xyz"

    def test_imgur_page_link_no_preview_returns_none(self):
        post = make_saved_post(url="https://imgur.com/abcdef")
        assert RedditIngestionAdapter._extract_image_url(post) is None

    def test_preview_fallback_used_for_gallery_posts(self):
        post = make_saved_post(url="https://www.reddit.com/gallery/abc123")
        post["preview"] = {
            "images": [{"source": {"url": "https://preview.redd.it/gallery_cover.jpg?auto=webp&amp;s=1"}}]
        }
        result = RedditIngestionAdapter._extract_image_url(post)
        assert result == "https://preview.redd.it/gallery_cover.jpg?auto=webp&s=1"

    def test_no_url_returns_none(self):
        post = make_saved_post(url="")
        assert RedditIngestionAdapter._extract_image_url(post) is None

    def test_video_post_no_preview_returns_none(self):
        post = make_saved_post(url="https://v.redd.it/somevideo")
        assert RedditIngestionAdapter._extract_image_url(post) is None


# ── _post_source_url ───────────────────────────────────────────────────────────

class TestPostSourceUrl:
    def test_relative_permalink_gets_domain_prepended(self):
        post = make_saved_post(permalink="/r/NieRAutomatafanart/comments/abc/title/")
        result = RedditIngestionAdapter._post_source_url(post)
        assert result == "https://www.reddit.com/r/NieRAutomatafanart/comments/abc/title/"

    def test_absolute_permalink_unchanged(self):
        post = make_saved_post(permalink="https://www.reddit.com/r/test/comments/xyz/")
        result = RedditIngestionAdapter._post_source_url(post)
        assert result == "https://www.reddit.com/r/test/comments/xyz/"

    def test_empty_permalink_returns_none(self):
        post = make_saved_post(permalink="")
        assert RedditIngestionAdapter._post_source_url(post) is None


# ── _download_image ────────────────────────────────────────────────────────────

class TestDownloadImage:
    def test_downloads_and_saves_file(self, tmp_path):
        fake_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_resp.content = fake_bytes
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        result = RedditIngestionAdapter._download_image(
            mock_client,
            "https://i.redd.it/testimage.jpg",
            tmp_path,
        )

        assert result is not None
        assert result.exists()
        assert result.read_bytes() == fake_bytes
        assert result.suffix == ".jpg"

    def test_skips_html_response(self, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
        mock_resp.content = b"<html>blocked</html>"
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        result = RedditIngestionAdapter._download_image(
            mock_client,
            "https://i.redd.it/blocked.jpg",
            tmp_path,
        )
        assert result is None

    def test_idempotent_skips_existing_file(self, tmp_path):
        existing = tmp_path / "existing.jpg"
        existing.write_bytes(b"already here")

        mock_client = MagicMock()

        result = RedditIngestionAdapter._download_image(
            mock_client,
            "https://i.redd.it/existing.jpg",
            tmp_path,
        )
        assert result == existing
        mock_client.get.assert_not_called()

    def test_http_error_returns_none(self, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403", request=MagicMock(), response=mock_resp
        )

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        result = RedditIngestionAdapter._download_image(
            mock_client,
            "https://i.redd.it/forbidden.jpg",
            tmp_path,
        )
        assert result is None

    def test_url_without_extension_uses_md5_stem(self, tmp_path):
        import hashlib
        fake_bytes = b"\xff\xd8\xff" + b"\x00" * 50
        url = "https://i.redd.it/noextension"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_resp.content = fake_bytes
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        result = RedditIngestionAdapter._download_image(mock_client, url, tmp_path)

        assert result is not None
        expected_stem = hashlib.md5(url.encode()).hexdigest()[:12]
        assert result.stem == expected_stem
        assert result.suffix == ".jpg"


# ── _fetch_saved_page ──────────────────────────────────────────────────────────

class TestFetchSavedPage:
    def _make_adapter(self, cookies_file, work_dir):
        return RedditIngestionAdapter(
            username="testuser",
            cookies_file=cookies_file,
            work_dir=work_dir,
        )

    def test_returns_posts_and_cursor(self, cookies_file, work_dir):
        response_json = {
            "data": {
                "after": "t3_nextpage",
                "children": [
                    {"kind": "t3", "data": {"id": "post1", "title": "Post 1"}},
                    {"kind": "t1", "data": {"id": "comment1", "body": "a comment"}},
                ],
            }
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response_json

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        adapter = self._make_adapter(cookies_file, work_dir)
        posts, after = adapter._fetch_saved_page(mock_client, after=None)

        assert after == "t3_nextpage"
        assert len(posts) == 2
        # _kind is injected onto each post's data dict
        assert posts[0]["_kind"] == "t3"
        assert posts[1]["_kind"] == "t1"

    def test_none_after_when_last_page(self, cookies_file, work_dir):
        response_json = {
            "data": {
                "after": None,
                "children": [{"kind": "t3", "data": {"id": "lastpost"}}],
            }
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response_json

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        adapter = self._make_adapter(cookies_file, work_dir)
        posts, after = adapter._fetch_saved_page(mock_client, after=None)

        assert after is None
        assert len(posts) == 1

    def test_403_raises_permission_error(self, cookies_file, work_dir):
        mock_resp = MagicMock()
        mock_resp.status_code = 403

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        adapter = self._make_adapter(cookies_file, work_dir)
        with pytest.raises(PermissionError, match="403"):
            adapter._fetch_saved_page(mock_client, after=None)

    def test_non_200_returns_empty(self, cookies_file, work_dir):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp

        adapter = self._make_adapter(cookies_file, work_dir)
        posts, after = adapter._fetch_saved_page(mock_client, after=None)

        assert posts == []
        assert after is None


# ── fetch_items integration ────────────────────────────────────────────────────

class TestFetchItems:
    def test_raises_without_username(self, cookies_file, work_dir, db):
        adapter = RedditIngestionAdapter(
            username="",
            cookies_file=cookies_file,
            work_dir=work_dir,
        )
        with pytest.raises(ValueError, match="username"):
            adapter.fetch_items(db, batch_size=5)

    def test_raises_without_cookies_file(self, work_dir, db):
        adapter = RedditIngestionAdapter(
            username="testuser",
            cookies_file=Path("/nonexistent/cookies.txt"),
            work_dir=work_dir,
        )
        with pytest.raises(ValueError, match="cookies file not found"):
            adapter.fetch_items(db, batch_size=5)

    def test_comments_in_saved_list_are_skipped(self, cookies_file, work_dir, db):
        comment = make_saved_post(kind="t1")  # t1 = comment
        image_post = make_saved_post(
            post_id="imgpost",
            url="https://i.redd.it/imgpost.jpg",
            permalink="/r/NieRAutomatafanart/comments/imgpost/title/",
            kind="t3",
        )
        fake_bytes = b"\xff\xd8\xff" + b"\x00" * 50

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_resp.content = fake_bytes
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.object(
                RedditIngestionAdapter,
                "_fetch_saved_page",
                return_value=([comment, image_post], None),
            ),
            patch.object(RedditIngestionAdapter, "_build_client") as mock_build,
            patch("time.sleep"),
        ):
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_build.return_value = mock_client

            adapter = RedditIngestionAdapter(
                username="testuser",
                cookies_file=cookies_file,
                work_dir=work_dir,
            )
            items = adapter.fetch_items(db, batch_size=5)

        # Only the image post (t3) should be returned — comment (t1) skipped
        assert len(items) == 1
        assert "imgpost" in items[0].source_url

    def test_non_image_posts_skipped(self, cookies_file, work_dir, db):
        # A text post with no image URL or preview
        text_post = make_saved_post(url="https://www.reddit.com/r/test/comments/abc/")
        text_post["preview"] = None

        with (
            patch.object(
                RedditIngestionAdapter,
                "_fetch_saved_page",
                return_value=([text_post], None),
            ),
            patch.object(RedditIngestionAdapter, "_build_client") as mock_build,
        ):
            mock_build.return_value = MagicMock()

            adapter = RedditIngestionAdapter(
                username="testuser",
                cookies_file=cookies_file,
                work_dir=work_dir,
            )
            items = adapter.fetch_items(db, batch_size=5)

        assert items == []

    def test_respects_batch_size(self, cookies_file, work_dir, db):
        posts = [
            make_saved_post(
                post_id=f"post{i}",
                url=f"https://i.redd.it/post{i}.jpg",
                permalink=f"/r/test/comments/post{i}/title/",
            )
            for i in range(10)
        ]
        fake_bytes = b"\xff\xd8\xff" + b"\x00" * 50

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_resp.content = fake_bytes
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.object(
                RedditIngestionAdapter,
                "_fetch_saved_page",
                return_value=(posts, None),
            ),
            patch.object(RedditIngestionAdapter, "_build_client") as mock_build,
            patch("time.sleep"),
        ):
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_build.return_value = mock_client

            adapter = RedditIngestionAdapter(
                username="testuser",
                cookies_file=cookies_file,
                work_dir=work_dir,
            )
            items = adapter.fetch_items(db, batch_size=3)

        assert len(items) == 3

    def test_skips_duplicates(self, cookies_file, work_dir, db):
        post = make_saved_post(
            post_id="dup1",
            url="https://i.redd.it/dup1.jpg",
            permalink="/r/test/comments/dup1/title/",
        )
        db.scalar.return_value = 99  # truthy = already in DB

        with (
            patch.object(
                RedditIngestionAdapter,
                "_fetch_saved_page",
                return_value=([post], None),
            ),
            patch.object(RedditIngestionAdapter, "_build_client") as mock_build,
        ):
            mock_build.return_value = MagicMock()

            adapter = RedditIngestionAdapter(
                username="testuser",
                cookies_file=cookies_file,
                work_dir=work_dir,
            )
            items = adapter.fetch_items(db, batch_size=5)

        assert items == []

    def test_skips_posts_below_min_score(self, cookies_file, work_dir, db):
        post = make_saved_post(score=3)

        with (
            patch.object(
                RedditIngestionAdapter,
                "_fetch_saved_page",
                return_value=([post], None),
            ),
            patch.object(RedditIngestionAdapter, "_build_client") as mock_build,
        ):
            mock_build.return_value = MagicMock()

            adapter = RedditIngestionAdapter(
                username="testuser",
                cookies_file=cookies_file,
                work_dir=work_dir,
                min_score=10,
            )
            items = adapter.fetch_items(db, batch_size=5)

        assert items == []

    def test_platform_context_has_all_enrichment_fields(self, cookies_file, work_dir, db):
        """Verify platform_context shape matches what enrichment.py reads."""
        post = make_saved_post(
            post_id="ctx1",
            url="https://i.redd.it/ctx1.jpg",
            permalink="/r/NieRAutomatafanart/comments/ctx1/title/",
            title="Beautiful 2B artwork",
            author="great_artist",
            flair="Fanart",
            score=250,
            over_18=False,
            subreddit="NieRAutomatafanart",
        )
        fake_bytes = b"\xff\xd8\xff" + b"\x00" * 50

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_resp.content = fake_bytes
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.object(
                RedditIngestionAdapter,
                "_fetch_saved_page",
                return_value=([post], None),
            ),
            patch.object(RedditIngestionAdapter, "_build_client") as mock_build,
            patch("time.sleep"),
        ):
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_build.return_value = mock_client

            adapter = RedditIngestionAdapter(
                username="testuser",
                cookies_file=cookies_file,
                work_dir=work_dir,
            )
            items = adapter.fetch_items(db, batch_size=5)

        assert len(items) == 1
        ctx = items[0].platform_context

        # Fields enrichment.py reads from platform_context for Reddit
        assert ctx["subreddit"] == "NieRAutomatafanart"
        assert ctx["title"] == "Beautiful 2B artwork"
        assert ctx["flair"] == "Fanart"
        assert ctx["author"] == "great_artist"
        assert ctx["score"] == 250
        assert ctx["nsfw"] is False
        assert items[0].source_platform_name == "Reddit"

    def test_pagination_stops_when_no_after_cursor(self, cookies_file, work_dir, db):
        """Adapter should stop paginating when Reddit returns after=None."""
        page1 = [make_saved_post(
            post_id="p1",
            url="https://i.redd.it/p1.jpg",
            permalink="/r/test/comments/p1/t/",
        )]
        fake_bytes = b"\xff\xd8\xff" + b"\x00" * 50

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "image/jpeg"}
        mock_resp.content = fake_bytes
        mock_resp.raise_for_status = MagicMock()

        # First call returns one post with after=None (last page)
        fetch_mock = MagicMock(return_value=(page1, None))

        with (
            patch.object(RedditIngestionAdapter, "_fetch_saved_page", fetch_mock),
            patch.object(RedditIngestionAdapter, "_build_client") as mock_build,
            patch("time.sleep"),
        ):
            mock_client = MagicMock()
            mock_client.get.return_value = mock_resp
            mock_build.return_value = mock_client

            adapter = RedditIngestionAdapter(
                username="testuser",
                cookies_file=cookies_file,
                work_dir=work_dir,
            )
            items = adapter.fetch_items(db, batch_size=10)

        # Should only have called _fetch_saved_page once
        assert fetch_mock.call_count == 1
        assert len(items) == 1
