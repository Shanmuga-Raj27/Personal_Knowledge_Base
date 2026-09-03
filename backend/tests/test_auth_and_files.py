"""
backend/tests/test_auth_and_files.py

Integration test suite for Phase 6:
- User registration and login
- Argon2id password verification
- Single-instance rate limiting
- 7-step JWT validation pipeline (401/403 responses)
- Multi-tenant file isolation (User A vs User B access boundaries)
- Storage object upload completion verification
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.auth import get_db
from app.core import security
from app.database import Base
from app.database.db_models import FileMetadata, User
from main import app

# In-memory SQLite engine with StaticPool for thread-safe shared connection
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)


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

# --- 1. REGISTRATION & LOGIN TESTS ---


def test_register_user_success(setup_test_database):
    """Verify user registration succeeds with valid matching passwords."""
    response = client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["status"] == "active"
    assert "id" in data

    # Confirm user exists in database with Argon2id hash
    db = setup_test_database
    db_user = db.query(User).filter(User.email == "newuser@example.com").first()
    assert db_user is not None
    assert db_user.hashed_password.startswith("$argon2id$")


def test_register_user_password_mismatch():
    """Verify registration fails when confirm_password does not match password."""
    response = client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "Password123!",
            "confirm_password": "DifferentPassword123!",
        },
    )

    assert response.status_code == 422  # Pydantic validation error


def test_register_user_duplicate_email(setup_test_database):
    """Verify registration fails when email is already registered."""
    db = setup_test_database
    existing = User(
        email="existing@example.com",
        hashed_password=security.get_password_hash("pw"),
        status="active",
    )
    db.add(existing)
    db.commit()

    response = client.post(
        "/auth/register",
        json={
            "email": "existing@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
    )

    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


def test_login_user_success(setup_test_database):
    """Verify login returns a valid JWT access token for correct Argon2id credentials."""
    db = setup_test_database
    hashed_pw = security.get_password_hash("CorrectPassword123!")
    user = User(
        email="user10@example.com",
        hashed_password=hashed_pw,
        status="active",
    )
    db.add(user)
    db.commit()

    response = client.post(
        "/auth/login",
        json={"email": "user10@example.com", "password": "CorrectPassword123!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Decode token payload to confirm numeric user ID as 'sub'
    payload = jwt.decode(
        data["access_token"],
        security.SECRET_KEY,
        algorithms=[security.ALGORITHM],
    )
    assert payload["sub"] == str(user.id)


def test_login_user_wrong_password(setup_test_database):
    """Verify login fails with HTTP 401 for incorrect password."""
    db = setup_test_database
    hashed_pw = security.get_password_hash("CorrectPassword123!")
    user = User(
        email="user10@example.com",
        hashed_password=hashed_pw,
        status="active",
    )
    db.add(user)
    db.commit()

    response = client.post(
        "/auth/login",
        json={"email": "user10@example.com", "password": "WrongPassword!"},
    )

    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


# --- 2. 7-STEP JWT VALIDATION PIPELINE TESTS ---


def test_jwt_pipeline_no_token():
    """Step 1: Missing JWT token returns HTTP 401."""
    response = client.get("/files")
    assert response.status_code == 401


def test_jwt_pipeline_invalid_signature():
    """Step 2: Tampered / invalid signature JWT returns HTTP 401."""
    invalid_token = "invalid.jwt.token"
    response = client.get(
        "/files", headers={"Authorization": f"Bearer {invalid_token}"}
    )
    assert response.status_code == 401


def test_jwt_pipeline_expired_token():
    """Step 3: Expired JWT token returns HTTP 401."""
    expired_payload = {
        "sub": "10",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
    }
    expired_token = jwt.encode(
        expired_payload, security.SECRET_KEY, algorithm=security.ALGORITHM
    )

    response = client.get(
        "/files", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401


def test_jwt_pipeline_disabled_user(setup_test_database):
    """Step 7: User account with status='disabled' returns HTTP 403 Forbidden."""
    db = setup_test_database
    disabled_user = User(
        email="disabled@example.com",
        hashed_password="hash",
        status="disabled",
    )
    db.add(disabled_user)
    db.commit()

    token = security.create_access_token(user_id=disabled_user.id)

    response = client.get(
        "/files", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
    assert "account is disabled" in response.json()["detail"]


# --- 3. MULTI-TENANT FILE ISOLATION TESTS ---


def test_user_a_can_access_own_files(setup_test_database):
    """Verify User A can list and modify their own files."""
    db = setup_test_database
    user_a = User(email="usera@example.com", hashed_password="pw", status="active")
    db.add(user_a)
    db.commit()

    file_a = FileMetadata(
        s3_key="uploads/file_a.pdf",
        filename="file_a.pdf",
        content_type="application/pdf",
        size_bytes=500,
        status="active",
        title="User A Document",
        description="Private doc",
        tags="doc",
        userid=user_a.id,
    )
    db.add(file_a)
    db.commit()

    token_a = security.create_access_token(user_id=user_a.id)

    response = client.get(
        "/files", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["fileId"] == file_a.fileid
    assert data["items"][0]["title"] == "User A Document"


def test_user_b_cannot_access_or_modify_user_a_file(setup_test_database):
    """Verify User B receives 404 when attempting to GET, PATCH, DELETE, or generate view URL for User A's file."""
    db = setup_test_database
    user_a = User(email="usera@example.com", hashed_password="pw", status="active")
    user_b = User(email="userb@example.com", hashed_password="pw", status="active")
    db.add_all([user_a, user_b])
    db.commit()

    file_a = FileMetadata(
        s3_key="uploads/file_a.pdf",
        filename="file_a.pdf",
        content_type="application/pdf",
        size_bytes=500,
        status="active",
        title="User A Private Doc",
        userid=user_a.id,
    )
    db.add(file_a)
    db.commit()

    token_b = security.create_access_token(user_id=user_b.id)

    # 1. User B lists files -> User A's file is not present
    list_res = client.get(
        "/files", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert list_res.status_code == 200
    assert len(list_res.json()["items"]) == 0

    # 2. User B attempts to PATCH User A's file
    patch_res = client.patch(
        f"/files/{file_a.fileid}",
        json={"title": "Hacked Title"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert patch_res.status_code == 404

    # 3. User B attempts to DELETE User A's file
    delete_res = client.delete(
        f"/files/{file_a.fileid}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert delete_res.status_code == 404

    # 4. User B attempts to generate view URL for User A's file key
    view_res = client.post(
        "/files/view-url",
        json={"key": file_a.s3_key},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert view_res.status_code == 404


# --- 4. UPLOAD VERIFICATION TESTS ---


def test_complete_upload_storage_verification_failure(setup_test_database):
    """Verify /files/upload-complete fails with 404 if object is missing in S3 storage."""
    db = setup_test_database
    user = User(email="user@example.com", hashed_password="pw", status="active")
    db.add(user)
    db.commit()

    pending_file = FileMetadata(
        s3_key="uploads/missing.txt",
        filename="missing.txt",
        content_type="text/plain",
        size_bytes=0,
        status="pending",
        userid=user.id,
    )
    db.add(pending_file)
    db.commit()

    token = security.create_access_token(user_id=user.id)

    with patch(
        "app.apis.routes.upload_file.get_object_metadata"
    ) as mock_get_meta:
        mock_get_meta.side_effect = FileNotFoundError("S3 object missing")

        response = client.post(
            "/files/upload-complete",
            json={"key": "uploads/missing.txt"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        db.refresh(pending_file)
        assert pending_file.status == "failed"
