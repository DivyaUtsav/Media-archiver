"""
Import artwork from Reddit saved_posts.csv (Reddit data export).

Processes the CSV in batches, tracking progress so runs can be interrupted
and resumed. Each run fetches the post JSON for each row, extracts an image
URL if present, downloads it, and feeds it into the standard ingestion +
enrichment pipeline.

Usage:
    python scripts/run_reddit_csv_import.py
    python scripts/run_reddit_csv_import.py --batch-size 50
    python scripts/run_reddit_csv_import.py --no-enrich
    python scripts/run_reddit_csv_import.py --status
    python scripts/run_reddit_csv_import.py --reset-progress

Place saved_posts.csv in backend/ (next to .env), or set:
    MEDIA_ARCHIVE_REDDIT_CSV_PATH=C:/full/path/to/saved_posts.csv
"""

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
from app.services.ingestion_adapters import RedditCSVIngestionAdapter


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import artwork from Reddit saved_posts.csv backlog."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.ingestion_batch_size,
        help=f"Posts to process per run (default: {settings.ingestion_batch_size}).",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip enrichment after ingestion.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print progress summary and exit without processing anything.",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="Clear the progress file so the next run starts from the beginning.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Path to saved_posts.csv (overrides MEDIA_ARCHIVE_REDDIT_CSV_PATH).",
    )
    args = parser.parse_args()

    adapter = RedditCSVIngestionAdapter(
        csv_path=args.csv,
    )

    if args.reset_progress:
        adapter.reset_progress()
        print("Progress reset. Run again without --reset-progress to start importing.")
        return

    if args.status:
        summary = adapter.progress_summary()
        total = summary["total"]
        seen = summary["seen"]
        remaining = summary["remaining"]
        pct = (seen / total * 100) if total else 0
        print(f"CSV import progress: {seen}/{total} rows seen ({pct:.1f}%), {remaining} remaining")
        return

    Base.metadata.create_all(bind=engine)

    print(f"Starting CSV import (batch_size={args.batch_size})...")
    summary = adapter.progress_summary()
    print(
        f"Progress: {summary['seen']}/{summary['total']} rows already processed, "
        f"{summary['remaining']} remaining"
    )

    with SessionLocal() as db:
        ingest_stats = run_ingestion(db=db, adapter=adapter)

    print(
        f"\nIngestion complete: fetched={ingest_stats.fetched}, "
        f"dropped_to_handoff={ingest_stats.dropped_to_handoff}"
    )

    # Print updated progress after the batch
    summary = adapter.progress_summary()
    remaining = summary["remaining"]
    total = summary["total"]
    seen = summary["seen"]
    pct = (seen / total * 100) if total else 0
    print(f"Progress: {seen}/{total} rows seen ({pct:.1f}%), {remaining} remaining")

    if remaining > 0:
        print(f"Run again to continue — {remaining} rows left.")
    else:
        print("All rows processed.")

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
