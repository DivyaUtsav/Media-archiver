import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import models  # noqa: F401
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.enrichment import run_enrichment
from app.services.ingestion import run_ingestion
from app.services.ingestion_adapters import get_ingestion_adapter


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ingestion (and optionally enrichment).")
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip the enrichment phase after ingestion (runs enrichment by default).",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    adapter = get_ingestion_adapter(settings.ingestion_adapter)

    with SessionLocal() as db:
        ingest_stats = run_ingestion(db=db, adapter=adapter)
    print(
        f"Ingestion complete: fetched={ingest_stats.fetched}, "
        f"skipped_duplicates={ingest_stats.skipped_duplicates}, "
        f"dropped_to_handoff={ingest_stats.dropped_to_handoff}"
    )

    if args.no_enrich:
        print("Skipping enrichment (--no-enrich flag set).")
        return

    print("\nStarting enrichment...")
    with SessionLocal() as db:
        enrich_stats = run_enrichment(db)
    print(
        f"Enrichment complete: processed={enrich_stats.processed}, "
        f"moved_to_gallery={enrich_stats.moved_to_gallery}, "
        f"moved_to_pending={enrich_stats.moved_to_pending}"
    )


if __name__ == "__main__":
    main()
