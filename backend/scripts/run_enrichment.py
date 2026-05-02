import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import models  # noqa: F401
from app.database import Base, SessionLocal, engine
from app.services.enrichment import run_enrichment


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        stats = run_enrichment(db)
    print(
        f"Enrichment complete: processed={stats.processed}, "
        f"moved_to_gallery={stats.moved_to_gallery}, moved_to_pending={stats.moved_to_pending}"
    )


if __name__ == "__main__":
    main()
