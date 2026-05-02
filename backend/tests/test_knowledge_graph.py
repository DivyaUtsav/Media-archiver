"""
Tests for knowledge graph endpoints — verifies LLD §3.3 response shapes,
duplicate detection, and the new /source-platforms endpoint.
"""

from app.models import Series, SourcePlatform


def test_post_series_returns_created_at(client):
    response = client.post("/series", json={"name": "Fullmetal Alchemist"})
    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] > 0
    assert payload["name"] == "Fullmetal Alchemist"
    assert "created_at" in payload
    assert payload["created_at"] is not None


def test_post_series_duplicate_returns_409(client):
    client.post("/series", json={"name": "Naruto"})
    response = client.post("/series", json={"name": "naruto"})  # case-insensitive
    assert response.status_code == 409


def test_post_character_returns_nested_series_and_created_at(client, db_session):
    series = Series(name="One Piece")
    db_session.add(series)
    db_session.commit()
    db_session.refresh(series)

    response = client.post("/characters", json={"name": "Nami", "series_id": series.id})
    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] > 0
    assert payload["name"] == "Nami"
    assert "created_at" in payload
    assert payload["created_at"] is not None
    # LLD §3.3 — series must be a nested object, not a raw series_id
    assert isinstance(payload["series"], dict)
    assert payload["series"]["id"] == series.id
    assert payload["series"]["name"] == "One Piece"


def test_post_character_unknown_series_returns_404(client):
    response = client.post("/characters", json={"name": "Ghost", "series_id": 9999})
    assert response.status_code == 404


def test_post_character_duplicate_returns_409(client, db_session):
    series = Series(name="Bleach")
    db_session.add(series)
    db_session.commit()
    db_session.refresh(series)

    client.post("/characters", json={"name": "Ichigo", "series_id": series.id})
    response = client.post("/characters", json={"name": "ichigo", "series_id": series.id})
    assert response.status_code == 409


def test_post_artist_returns_created_at(client):
    response = client.post("/artists", json={"name": "ArtistX"})
    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] > 0
    assert payload["name"] == "ArtistX"
    assert "created_at" in payload
    assert payload["created_at"] is not None


def test_post_artist_duplicate_returns_409(client):
    client.post("/artists", json={"name": "ArtistY"})
    response = client.post("/artists", json={"name": "artisty"})
    assert response.status_code == 409


def test_get_source_platforms_returns_list(client, db_session):
    db_session.add_all([SourcePlatform(name="Pixiv"), SourcePlatform(name="ArtStation")])
    db_session.commit()

    response = client.get("/source-platforms")
    assert response.status_code == 200
    items = response.json()["items"]
    names = [i["name"] for i in items]
    assert "Pixiv" in names
    assert "ArtStation" in names
    # Verify each item has id + name
    for item in items:
        assert "id" in item
        assert "name" in item


def test_get_source_platforms_empty(client):
    response = client.get("/source-platforms")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_list_series_characters_endpoint(client, db_session):
    series = Series(name="Attack on Titan")
    db_session.add(series)
    db_session.commit()
    db_session.refresh(series)

    client.post("/characters", json={"name": "Eren", "series_id": series.id})
    client.post("/characters", json={"name": "Mikasa", "series_id": series.id})

    response = client.get(f"/series/{series.id}/characters")
    assert response.status_code == 200
    payload = response.json()
    assert payload["series"]["id"] == series.id
    names = [c["name"] for c in payload["characters"]]
    assert "Eren" in names
    assert "Mikasa" in names


def test_list_series_unknown_returns_404(client):
    response = client.get("/series/9999/characters")
    assert response.status_code == 404
