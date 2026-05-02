from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.config import settings
from app.database import get_db
from app.main import app


@pytest.fixture()
def db_session(tmp_path) -> Generator[Session, None, None]:
    db_path = tmp_path / "test_media_archive.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session
    engine.dispose()


@pytest.fixture()
def client(db_session: Session, tmp_path) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    settings.archive_root = tmp_path / "archive"
    settings.archive_root.mkdir(parents=True, exist_ok=True)
    settings.handoff_root = tmp_path / "handoff"
    settings.handoff_root.mkdir(parents=True, exist_ok=True)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
