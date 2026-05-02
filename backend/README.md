# Personal Media Archive Backend

Initial backend scaffold from the project Concept/HLD/LLD.

## Run locally

1. Create and activate virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Start API server:
   - `uvicorn app.main:app --reload`

The API docs are available at `http://127.0.0.1:8000/docs`.

Health endpoints:
- `GET /health` basic API liveness
- `GET /health/providers` provider readiness snapshot (Ollama/HuggingFace checks)

## Run ingestion + enrichment (backend-only phase)

Ingestion and enrichment are chained by default. Running ingestion will automatically trigger enrichment on the handoff folder when complete.

1. Initialize DB:
   - `python scripts/init_db.py`
2. Copy example manifest and edit file paths:
   - `copy ingestion_manifest.example.json ingestion_manifest.json`
3. Run ingestion (and enrichment):
   - `python scripts/run_ingestion.py`
   - Add `--no-enrich` to skip enrichment: `python scripts/run_ingestion.py --no-enrich`

Environment variables (optional):

- `MEDIA_ARCHIVE_INGESTION_ADAPTER` = `manifest` (default) or `gallery-dl`
- `MEDIA_ARCHIVE_INGESTION_MANIFEST_PATH` = path to ingestion manifest JSON
- `MEDIA_ARCHIVE_HANDOFF_ROOT` = handoff folder path
- `MEDIA_ARCHIVE_GALLERY_DL_TARGETS` = comma-separated target URLs or usernames for `gallery-dl`
- `MEDIA_ARCHIVE_GALLERY_DL_EXTRA_ARGS` = comma-separated CLI args appended to `gallery-dl`

### Gallery-DL mode

Set:

- `MEDIA_ARCHIVE_INGESTION_ADAPTER=gallery-dl`
- `MEDIA_ARCHIVE_GALLERY_DL_TARGETS=<target1>,<target2>`

Then run:

- `python scripts/run_ingestion.py`

The adapter runs `gallery-dl --write-metadata`, scans `ingestion_work/` for downloaded files plus metadata, and converts them into the same ingestion flow (dedup + handoff + DB records), then immediately triggers enrichment.

## Run enrichment only

- `python scripts/run_enrichment.py`

Current enrichment implementation performs:
- sidecar scan from `handoff/`
- knowledge graph text matching (characters/artists/platform)
- optional provider integrations:
  - text extraction: `none` or `ollama`
  - content rating: `none` or `huggingface`
  - art type: `none` or `ollama`
- confidence routing to `gallery` or `pending_review` (LLD threshold rules)
- pending-category suggestion writes into `artwork_pending_tags`
- media move to archive destination (`_pending`, `_multi_series`, or series folder)
- sets `file_missing=True` on DB record if file move fails (OSError)

If a provider is set to `none`, enrichment does not guess values and unresolved categories remain pending.

Provider env vars:
- `MEDIA_ARCHIVE_ENRICHMENT_TEXT_PROVIDER` = `none` or `ollama`
- `MEDIA_ARCHIVE_ENRICHMENT_CONTENT_PROVIDER` = `none` or `huggingface`
- `MEDIA_ARCHIVE_ENRICHMENT_ART_TYPE_PROVIDER` = `none` or `ollama`
- `MEDIA_ARCHIVE_OLLAMA_BASE_URL`, `MEDIA_ARCHIVE_OLLAMA_TEXT_MODEL`, `MEDIA_ARCHIVE_OLLAMA_VISION_MODEL`
- `MEDIA_ARCHIVE_HUGGINGFACE_MODEL`
- `MEDIA_ARCHIVE_ENRICHMENT_STRICT_PROVIDERS` = `true/false`
- `MEDIA_ARCHIVE_PROVIDER_STARTUP_CHECKS` = `true/false` (cache checks at startup)

## API surface

| Method | Path | Description |
|---|---|---|
| GET | `/artworks` | Gallery list with pagination + filters |
| GET | `/artworks/{id}` | Artwork detail |
| GET | `/artworks/{id}/media` | Serve media file (410 if file_missing) |
| PATCH | `/artworks/{id}/tags` | Update tags manually |
| GET | `/queue/count` | Pending review count |
| GET | `/queue/next` | Next pending artwork + suggestions |
| POST | `/queue/{id}/complete` | Resolve pending artwork |
| GET | `/series` | List series with counts |
| GET | `/series/{id}/characters` | Characters for a series |
| POST | `/series` | Create series |
| GET | `/characters` | Search characters |
| POST | `/characters` | Create character |
| GET | `/artists` | Search artists |
| POST | `/artists` | Create artist |
| GET | `/source-platforms` | List all known source/publication platforms |
| GET | `/health` | Liveness |
| GET | `/health/providers` | Provider readiness |
