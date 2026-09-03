import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from main import app
from app.database import get_db
from app.auth.auth_dependencies import get_current_user
from app.database.db_models import FileMetadata, User

client = TestClient(app)

# Setup mock database session and test user
mock_db_session = MagicMock()
mock_test_user = User(id=42, email="test@example.com", hashed_password="pw", status="active")


def override_get_db():
    yield mock_db_session


def override_get_current_user():
    return mock_test_user


@pytest.fixture(autouse=True)
def setup_dependency_overrides():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    mock_db_session.reset_mock()
    def mock_refresh(obj):
        if hasattr(obj, "fileid") and obj.fileid is None:
            obj.fileid = 42
    mock_db_session.refresh.side_effect = mock_refresh
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_get_upload_url_route_success():
    with patch("app.apis.routes.document_routes.create_presigned_put_url") as mock_create:
        mock_create.return_value = {
            "upload_url": "https://s3.example.com/uploads/123_test.txt",
            "key": "uploads/123_test.txt",
            "expires_in": 300,
        }

        response = client.post(
            "/files/upload-url",
            json={"filename": "test.txt", "contentType": "text/plain"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["uploadUrl"] == "https://s3.example.com/uploads/123_test.txt"
        assert data["key"] == "uploads/123_test.txt"
        assert data["expires_in"] == 300
        assert data["fileId"] == 42

        # Verify DB insert occurred
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()


def test_complete_upload_route_success():
    with patch("app.apis.routes.document_routes.get_object_metadata") as mock_meta:
        mock_meta.return_value = {
            "size_bytes": 1024,
            "content_type": "text/plain",
        }

        mock_file = FileMetadata(
            fileid=42,
            s3_key="uploads/123_test.txt",
            filename="test.txt",
            content_type="text/plain",
            size_bytes=0,
            status="pending",
            title=None,
            description=None,
            tags=None,
            userid=42,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_db_session.query().filter().first.return_value = mock_file

        response = client.post(
            "/files/upload-complete",
            json={"key": "uploads/123_test.txt", "filename": "test.txt"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert data["key"] == "uploads/123_test.txt"
        assert data["metadata"]["fileId"] == 42
        assert mock_file.status == "active"
        assert mock_file.size_bytes == 1024


def test_complete_upload_route_not_found():
    with patch("app.apis.routes.document_routes.get_object_metadata") as mock_meta:
        mock_meta.side_effect = FileNotFoundError("Object not found in storage.")

        mock_file = FileMetadata(
            fileid=99,
            s3_key="uploads/missing.txt",
            filename="missing.txt",
            content_type="text/plain",
            size_bytes=0,
            status="pending",
            title=None,
            description=None,
            tags=None,
            userid=42,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db_session.query().filter().first.return_value = mock_file

        response = client.post(
            "/files/upload-complete",
            json={"key": "uploads/missing.txt"},
        )

        assert response.status_code == 404
        assert "Object not found in storage" in response.json()["detail"]
        assert mock_file.status == "failed"


def test_get_view_url_route_success():
    with patch("app.apis.routes.document_routes.create_presigned_get_url") as mock_create_get:
        mock_create_get.return_value = {
            "view_url": "https://s3.example.com/uploads/123_test.txt?auth=abc",
            "key": "uploads/123_test.txt",
            "expires_in": 300,
        }

        mock_file = FileMetadata(
            fileid=42,
            s3_key="uploads/123_test.txt",
            filename="test.txt",
            content_type="text/plain",
            size_bytes=100,
            status="active",
            userid=42,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db_session.query().filter().first.return_value = mock_file

        response = client.post(
            "/files/view-url",
            json={"key": "uploads/123_test.txt"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["viewUrl"] == "https://s3.example.com/uploads/123_test.txt?auth=abc"
        assert data["key"] == "uploads/123_test.txt"


def test_get_view_url_route_not_found():
    mock_db_session.query().filter().first.return_value = None

    response = client.post(
        "/files/view-url",
        json={"key": "uploads/missing.txt"},
    )

    assert response.status_code == 404
    assert "access denied" in response.json()["detail"].lower()


def test_list_files_route_success():
    mock_file = FileMetadata(
        fileid=42,
        s3_key="uploads/123_test.txt",
        filename="test.txt",
        content_type="text/plain",
        size_bytes=100,
        status="active",
        title="A Great Title",
        description="A Description",
        tags="tag1,tag2",
        userid=42,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_db_session.query().filter().order_by().all.return_value = [mock_file]

    response = client.get("/files")

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["fileId"] == 42
    assert data["items"][0]["title"] == "A Great Title"
    assert data["items"][0]["tags"] == "tag1,tag2"


def test_update_metadata_route_success():
    mock_file = FileMetadata(
        fileid=42,
        s3_key="uploads/123_test.txt",
        filename="test.txt",
        content_type="text/plain",
        size_bytes=100,
        status="active",
        title="Old Title",
        description="Old Desc",
        tags="oldtag",
        userid=42,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_db_session.query().filter().first.return_value = mock_file

    response = client.patch(
        "/files/42",
        json={
            "title": "New Title",
            "description": "New Desc",
            "tags": "newtag1,newtag2",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Title"
    assert data["description"] == "New Desc"
    assert data["tags"] == "newtag1,newtag2"

    assert mock_file.title == "New Title"
    assert mock_file.description == "New Desc"
    assert mock_file.tags == "newtag1,newtag2"
    mock_db_session.commit.assert_called_once()


def test_delete_file_route_success():
    with patch("app.apis.routes.document_routes.delete_s3_object") as mock_delete_s3, \
         patch("app.apis.routes.document_routes.delete_file_vector", AsyncMock(return_value=True)):
        mock_file = FileMetadata(
            fileid=42,
            s3_key="uploads/123_test.txt",
            filename="test.txt",
            content_type="text/plain",
            size_bytes=100,
            status="active",
            title="Title",
            description="Desc",
            tags="tag",
            userid=42,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db_session.query().filter().first.return_value = mock_file

        response = client.delete("/files/42")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["fileId"] == 42
        mock_delete_s3.assert_called_once_with("uploads/123_test.txt")
        mock_db_session.delete.assert_called_once_with(mock_file)
        mock_db_session.commit.assert_called_once()


def test_delete_file_route_not_found():
    mock_db_session.query().filter().first.return_value = None

    response = client.delete("/files/999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_delete_file_route_failed_s3():
    with patch("app.apis.routes.document_routes.delete_s3_object") as mock_delete_s3:
        mock_delete_s3.side_effect = RuntimeError("S3 delete failed")
        mock_file = FileMetadata(
            fileid=42,
            s3_key="uploads/123_test.txt",
            filename="test.txt",
            content_type="text/plain",
            size_bytes=100,
            status="active",
            title="Title",
            description="Desc",
            tags="tag",
            userid=42,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db_session.query().filter().first.return_value = mock_file

        response = client.delete("/files/42")

        assert response.status_code == 500
        assert "Failed to delete object from S3 storage" in response.json()["detail"]
        mock_db_session.delete.assert_not_called()


def test_delete_file_route_failed_qdrant():
    with patch("app.apis.routes.document_routes.delete_s3_object") as mock_delete_s3, \
         patch("app.apis.routes.document_routes.delete_file_vector", AsyncMock(return_value=False)):
        mock_file = FileMetadata(
            fileid=42,
            s3_key="uploads/123_test.txt",
            filename="test.txt",
            content_type="text/plain",
            size_bytes=100,
            status="active",
            title="Title",
            description="Desc",
            tags="tag",
            userid=42,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db_session.query().filter().first.return_value = mock_file

        response = client.delete("/files/42")

        assert response.status_code == 500
        assert "Failed to remove document vector embeddings" in response.json()["detail"]
        mock_delete_s3.assert_called_once_with("uploads/123_test.txt")
        mock_db_session.delete.assert_not_called()


def test_delete_file_route_failed_db():
    with patch("app.apis.routes.document_routes.delete_s3_object") as mock_delete_s3, \
         patch("app.apis.routes.document_routes.delete_file_vector", AsyncMock(return_value=True)):
        mock_file = FileMetadata(
            fileid=42,
            s3_key="uploads/123_test.txt",
            filename="test.txt",
            content_type="text/plain",
            size_bytes=100,
            status="active",
            title="Title",
            description="Desc",
            tags="tag",
            userid=42,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db_session.query().filter().first.return_value = mock_file
        mock_db_session.commit.side_effect = Exception("Database connection failure")

        response = client.delete("/files/42")

        assert response.status_code == 500
        assert "Database deletion failed after external storage" in response.json()["detail"]
        mock_delete_s3.assert_called_once_with("uploads/123_test.txt")
