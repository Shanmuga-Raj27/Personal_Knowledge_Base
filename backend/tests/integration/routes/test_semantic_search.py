"""
backend/tests/integration/routes/test_semantic_search.py

Integration tests for semantic AI file search endpoint (/files/search).
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

# In-memory SQLite engine with StaticPool
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


def test_semantic_search_empty_query_returns_all_active(setup_test_database):
    db = setup_test_database
    user = User(email="user@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()

    file1 = FileMetadata(
        s3_key="uploads/file1.pdf",
        filename="file1.pdf",
        status="active",
        title="File One",
        userid=user.id,
    )
    db.add(file1)
    db.commit()

    token = security.create_access_token(user_id=user.id)
    response = client.get(
        "/files/search?q=",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["searchMode"] == "none"
    assert data["status"] == "ok"
    assert len(data["results"]) == 1
    assert data["results"][0]["fileId"] == file1.fileid


def test_semantic_search_multi_tenant_isolation(setup_test_database):
    db = setup_test_database
    user_a = User(email="usera@example.com", hashed_password="pw", status="active")
    user_b = User(email="userb@example.com", hashed_password="pw", status="active")
    db.add_all([user_a, user_b])
    db.commit()

    file_a = FileMetadata(
        s3_key="uploads/a.pdf",
        filename="a.pdf",
        status="active",
        title="User A Spec",
        userid=user_a.id,
    )
    file_b = FileMetadata(
        s3_key="uploads/b.pdf",
        filename="b.pdf",
        status="active",
        title="User B Spec",
        userid=user_b.id,
    )
    db.add_all([file_a, file_b])
    db.commit()

    token_a = security.create_access_token(user_id=user_a.id)
    token_b = security.create_access_token(user_id=user_b.id)

    # Mock search_file_vectors returning both IDs [file_a.fileid, file_b.fileid]
    with patch("app.apis.routes.upload_file.search_file_vectors", AsyncMock(return_value=[file_a.fileid, file_b.fileid])):
        # User A searches -> Should ONLY return file_a
        res_a = client.get(
            "/files/search?q=spec",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res_a.status_code == 200
        data_a = res_a.json()
        assert data_a["searchMode"] == "semantic"
        assert data_a["status"] == "ok"
        assert len(data_a["results"]) == 1
        assert data_a["results"][0]["fileId"] == file_a.fileid

        # User B searches -> Should ONLY return file_b
        res_b = client.get(
            "/files/search?q=spec",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_b.status_code == 200
        data_b = res_b.json()
        assert data_b["searchMode"] == "semantic"
        assert data_b["status"] == "ok"
        assert len(data_b["results"]) == 1
        assert data_b["results"][0]["fileId"] == file_b.fileid


def test_semantic_search_unrelated_query_pig_returns_no_match(setup_test_database):
    db = setup_test_database
    user = User(email="user@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()

    resume_file = FileMetadata(
        s3_key="uploads/resume.pdf",
        filename="resume.pdf",
        status="active",
        title="Software Engineer Resume",
        description="Python FastAPI and React experience",
        userid=user.id,
    )
    db.add(resume_file)
    db.commit()

    token = security.create_access_token(user_id=user.id)
    # Search for completely unrelated term 'pig' -> score < 0.55 returns []
    with patch("app.apis.routes.upload_file.search_file_vectors", AsyncMock(return_value=[])):
        res = client.get(
            "/files/search?q=pig",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["searchMode"] == "semantic"
        assert data["status"] == "no_match"
        assert data["results"] == []
