"""
backend/tests/integration/routes/test_pagination.py

Integration tests for search and file listing pagination parameters and validation boundaries.
"""
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from app.auth.auth import get_db
from app.core import security
from app.database import Base
from app.database.db_models import FileMetadata, User

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_test_database():
    """Create all tables in memory before each test and drop them after."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


client = TestClient(app)


def test_list_files_pagination(setup_test_database):
    db = setup_test_database
    user = User(email="user@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()

    for i in range(15):
        file_item = FileMetadata(
            s3_key=f"uploads/file_{i}.pdf",
            filename=f"file_{i}.pdf",
            status="active",
            title=f"File {i}",
            userid=user.id,
        )
        db.add(file_item)
    db.commit()

    token = security.create_access_token(user_id=user.id)
    response = client.get(
        "/files?limit=10&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 15
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert len(data["items"]) == 10


def test_list_files_invalid_limit_returns_422(setup_test_database):
    db = setup_test_database
    user = User(email="user@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()
    token = security.create_access_token(user_id=user.id)

    response = client.get(
        "/files?limit=250",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_list_files_invalid_offset_returns_422(setup_test_database):
    db = setup_test_database
    user = User(email="user@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()
    token = security.create_access_token(user_id=user.id)

    response = client.get(
        "/files?offset=-1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_search_files_pagination(setup_test_database):
    db = setup_test_database
    user = User(email="user@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()

    created_files = []
    for i in range(10):
        file_item = FileMetadata(
            s3_key=f"uploads/test_{i}.pdf",
            filename=f"test_{i}.pdf",
            status="active",
            title=f"Test Document {i}",
            userid=user.id,
        )
        db.add(file_item)
        created_files.append(file_item)
    db.commit()

    token = security.create_access_token(user_id=user.id)

    mock_hits = [(f.fileid, 0.9 - (idx * 0.05)) for idx, f in enumerate(created_files)]

    with patch("app.apis.routes.upload_file.search_file_vectors", AsyncMock(return_value=mock_hits)):
        response = client.get(
            "/files/search?q=test&limit=5&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["searchMode"] == "semantic"
        assert data["total"] == 10
        assert data["limit"] == 5
        assert data["offset"] == 0
        assert len(data["results"]) == 5
