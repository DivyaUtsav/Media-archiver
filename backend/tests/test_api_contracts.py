from pathlib import Path

from sqlalchemy.orm import Session

from app.models import (
    Artwork,
    ArtworkArtist,
    ArtworkCharacter,
    ArtworkPendingTag,
    Artist,
    Character,
    Series,
    SourcePlatform,
)


def _seed_common_entities(db: Session):
    series_one = Series(name="One Piece")
    series_two = Series(name="Bleach")
    char_zoro = Character(name="Zoro", series=series_one)
    char_luffy = Character(name="Luffy", series=series_one)
    char_ichigo = Character(name="Ichigo", series=series_two)
    artist = Artist(name="ArtistA")
    platform = SourcePlatform(name="Pixiv")
    db.add_all([series_one, series_two, char_zoro, char_luffy, char_ichigo, artist, platform])
    db.commit()
    return {
        "series_one": series_one,
        "series_two": series_two,
        "char_zoro": char_zoro,
        "char_luffy": char_luffy,
        "char_ichigo": char_ichigo,
        "artist": artist,
        "platform": platform,
    }


def test_patch_artwork_tags_replaces_junction_and_marks_manual(client, db_session: Session, tmp_path):
    refs = _seed_common_entities(db_session)
    media = tmp_path / "img1.jpg"
    media.write_bytes(b"img")
    artwork = Artwork(
        file_path=str(media),
        source_url="https://reddit.com/post/1",
        status="gallery",
        content_rating="SFW",
        art_type="Artwork",
    )
    db_session.add(artwork)
    db_session.commit()
    db_session.refresh(artwork)
    db_session.add(
        ArtworkCharacter(artwork_id=artwork.id, character_id=refs["char_ichigo"].id, confidence=0.7, is_manual=False)
    )
    db_session.commit()

    response = client.patch(
        f"/artworks/{artwork.id}/tags",
        json={
            "content_rating": "NSFW",
            "art_type": "Cosplay",
            "characters": [refs["char_zoro"].id, refs["char_luffy"].id],
            "artists": [refs["artist"].id],
            "publication_platform_id": refs["platform"].id,
        },
    )
    assert response.status_code == 200

    refreshed = db_session.get(Artwork, artwork.id)
    assert refreshed is not None
    assert refreshed.content_rating == "NSFW"
    assert refreshed.content_rating_is_manual is True
    assert refreshed.content_rating_confidence is None
    assert refreshed.art_type == "Cosplay"
    assert refreshed.art_type_is_manual is True
    assert refreshed.publication_platform_id == refs["platform"].id
    assert refreshed.publication_platform_is_manual is True

    chars = db_session.query(ArtworkCharacter).filter(ArtworkCharacter.artwork_id == artwork.id).all()
    assert sorted(c.character_id for c in chars) == sorted([refs["char_zoro"].id, refs["char_luffy"].id])
    assert all(c.is_manual for c in chars)
    assert all(c.confidence is None for c in chars)

    artists = db_session.query(ArtworkArtist).filter(ArtworkArtist.artwork_id == artwork.id).all()
    assert [a.artist_id for a in artists] == [refs["artist"].id]
    assert artists[0].is_manual is True
    assert artists[0].confidence is None


def test_queue_complete_requires_pending_fields(client, db_session: Session, tmp_path):
    refs = _seed_common_entities(db_session)
    pending_dir = tmp_path / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    media = pending_dir / "queue1.jpg"
    media.write_bytes(b"img")
    artwork = Artwork(
        file_path=str(media),
        source_url="https://reddit.com/post/2",
        status="pending_review",
        content_rating="SFW",
        art_type="Artwork",
    )
    db_session.add(artwork)
    db_session.commit()
    db_session.refresh(artwork)

    db_session.add_all(
        [
            ArtworkPendingTag(artwork_id=artwork.id, tag_category="character", suggestion={"items": []}),
            ArtworkPendingTag(artwork_id=artwork.id, tag_category="artist", suggestion={"items": []}),
        ]
    )
    db_session.commit()

    bad_response = client.post(f"/queue/{artwork.id}/complete", json={"characters": [refs["char_zoro"].id]})
    assert bad_response.status_code == 400
    assert "artists" in bad_response.json()["detail"]

    ok_response = client.post(
        f"/queue/{artwork.id}/complete",
        json={"characters": [refs["char_zoro"].id], "artists": [refs["artist"].id]},
    )
    assert ok_response.status_code == 200
    payload = ok_response.json()
    assert payload["status"] == "gallery"

    moved = db_session.get(Artwork, artwork.id)
    assert moved is not None
    assert Path(moved.file_path).exists()
    assert "_pending" not in moved.file_path
    remaining_pending = db_session.query(ArtworkPendingTag).filter(ArtworkPendingTag.artwork_id == artwork.id).all()
    assert remaining_pending == []


def test_get_artworks_supports_combined_filters(client, db_session: Session, tmp_path):
    refs = _seed_common_entities(db_session)
    media1 = tmp_path / "a1.jpg"
    media2 = tmp_path / "a2.jpg"
    media1.write_bytes(b"1")
    media2.write_bytes(b"2")

    artwork_match = Artwork(
        file_path=str(media1),
        source_url="https://reddit.com/post/3",
        status="gallery",
        content_rating="SFW",
        art_type="Artwork",
    )
    artwork_other = Artwork(
        file_path=str(media2),
        source_url="https://reddit.com/post/4",
        status="gallery",
        content_rating="NSFW",
        art_type="Cosplay",
    )
    db_session.add_all([artwork_match, artwork_other])
    db_session.commit()
    db_session.refresh(artwork_match)
    db_session.refresh(artwork_other)

    db_session.add_all(
        [
            ArtworkCharacter(artwork_id=artwork_match.id, character_id=refs["char_zoro"].id, confidence=0.9, is_manual=False),
            ArtworkCharacter(artwork_id=artwork_other.id, character_id=refs["char_ichigo"].id, confidence=0.9, is_manual=False),
        ]
    )
    db_session.commit()

    response = client.get(
        "/artworks",
        params={
            "series_id": refs["series_one"].id,
            "character_id": refs["char_zoro"].id,
            "content_rating": "SFW",
            "art_type": "Artwork",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == artwork_match.id
    assert payload["items"][0]["series"][0]["name"] == "One Piece"


def test_series_endpoint_includes_character_and_artwork_counts(client, db_session: Session, tmp_path):
    refs = _seed_common_entities(db_session)
    media = tmp_path / "s1.jpg"
    media.write_bytes(b"1")
    artwork = Artwork(
        file_path=str(media),
        source_url="https://reddit.com/post/series-count",
        status="gallery",
        content_rating="SFW",
        art_type="Artwork",
    )
    db_session.add(artwork)
    db_session.commit()
    db_session.refresh(artwork)
    db_session.add_all(
        [
            ArtworkCharacter(artwork_id=artwork.id, character_id=refs["char_zoro"].id, confidence=0.9, is_manual=False),
            ArtworkCharacter(artwork_id=artwork.id, character_id=refs["char_luffy"].id, confidence=0.9, is_manual=False),
        ]
    )
    db_session.commit()

    response = client.get("/series")
    assert response.status_code == 200
    items = response.json()["items"]
    one_piece = next(item for item in items if item["id"] == refs["series_one"].id)
    bleach = next(item for item in items if item["id"] == refs["series_two"].id)

    assert one_piece["character_count"] == 2
    assert one_piece["artwork_count"] == 1
    assert bleach["character_count"] == 1
    assert bleach["artwork_count"] == 0


def test_characters_endpoint_includes_artwork_count(client, db_session: Session, tmp_path):
    refs = _seed_common_entities(db_session)
    media = tmp_path / "c1.jpg"
    media.write_bytes(b"1")
    artwork = Artwork(
        file_path=str(media),
        source_url="https://reddit.com/post/character-count",
        status="gallery",
        content_rating="SFW",
        art_type="Artwork",
    )
    db_session.add(artwork)
    db_session.commit()
    db_session.refresh(artwork)
    db_session.add(ArtworkCharacter(artwork_id=artwork.id, character_id=refs["char_zoro"].id, confidence=0.9, is_manual=False))
    db_session.commit()

    response = client.get("/characters", params={"series_id": refs["series_one"].id, "search": "Zo"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Zoro"
    assert items[0]["artwork_count"] == 1


def test_get_artwork_media_returns_410_when_file_missing_flag_set(client, db_session: Session, tmp_path):
    """file_missing=True on the record should immediately return 410 without touching disk."""
    artwork = Artwork(
        file_path=str(tmp_path / "gone.jpg"),
        source_url="https://reddit.com/post/missing-flag",
        status="gallery",
        file_missing=True,
    )
    db_session.add(artwork)
    db_session.commit()
    db_session.refresh(artwork)

    response = client.get(f"/artworks/{artwork.id}/media")
    assert response.status_code == 410


def test_get_artwork_media_sets_file_missing_and_returns_410_on_disk_miss(client, db_session: Session, tmp_path):
    """First request to a record whose file has disappeared from disk should set file_missing=True and return 410."""
    artwork = Artwork(
        file_path=str(tmp_path / "vanished.jpg"),  # file never created
        source_url="https://reddit.com/post/vanished",
        status="gallery",
        file_missing=False,
    )
    db_session.add(artwork)
    db_session.commit()
    db_session.refresh(artwork)

    response = client.get(f"/artworks/{artwork.id}/media")
    assert response.status_code == 410

    db_session.expire(artwork)
    refreshed = db_session.get(Artwork, artwork.id)
    assert refreshed.file_missing is True
