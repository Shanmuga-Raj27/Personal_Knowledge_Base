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
    assert data["total"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["file"]["fileId"] == file1.fileid


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

    # Mock search_file_vectors returning [(file_a.fileid, 0.89), (file_b.fileid, 0.85)]
    with patch("app.apis.routes.upload_file.search_file_vectors", AsyncMock(return_value=[(file_a.fileid, 0.89), (file_b.fileid, 0.85)])):
        # User A searches -> Should ONLY return file_a with score
        res_a = client.get(
            "/files/search?q=spec",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res_a.status_code == 200
        data_a = res_a.json()
        assert data_a["searchMode"] == "semantic"
        assert data_a["total"] == 1
        assert len(data_a["results"]) == 1
        assert data_a["results"][0]["file"]["fileId"] == file_a.fileid
        assert data_a["results"][0]["score"] == 0.89

        # User B searches -> Should ONLY return file_b with score
        res_b = client.get(
            "/files/search?q=spec",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_b.status_code == 200
        data_b = res_b.json()
        assert data_b["searchMode"] == "semantic"
        assert data_b["total"] == 1
        assert len(data_b["results"]) == 1
        assert data_b["results"][0]["file"]["fileId"] == file_b.fileid
        assert data_b["results"][0]["score"] == 0.85


def test_semantic_search_unrelated_query_pig_returns_clean_zero_matches(setup_test_database):
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
        assert data["total"] == 0
        assert data["results"] == []


def test_query_validation_returns_422(setup_test_database):
    db = setup_test_database
    user = User(email="user@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()
    token = security.create_access_token(user_id=user.id)

    # 101 character query -> 422
    long_query = "a" * 101
    res = client.get(f"/files/search?q={long_query}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 422

    # Whitespace only query -> 422
    res_space = client.get("/files/search?q=%20%20%20", headers={"Authorization": f"Bearer {token}"})
    assert res_space.status_code == 422


def test_infrastructure_failure_returns_503(setup_test_database):
    db = setup_test_database
    user = User(email="user@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()
    token = security.create_access_token(user_id=user.id)

    with patch("app.apis.routes.upload_file.search_file_vectors", AsyncMock(side_effect=RuntimeError("Qdrant connection refused"))):
        res = client.get("/files/search?q=test", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 503
        assert "Vector search service is currently unavailable" in res.json()["detail"]
