import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from main import app
from app.database import get_db
from app.database.db_models import FileMetadata

client = TestClient(app)

# Setup mock database session
mock_db_session = MagicMock()


def override_get_db():
    yield mock_db_session


# Apply dependency override
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def reset_db_mock():
    mock_db_session.reset_mock()
    # Default refresh mock to set a dummy primary key
    def mock_refresh(obj):
        obj.fileid = 42
    mock_db_session.refresh.side_effect = mock_refresh


def test_get_upload_url_route_success():
    with patch("app.apis.routes.upload_file.create_presigned_put_url") as mock_create:
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
    with patch("app.apis.routes.upload_file.get_object_metadata") as mock_meta:
        mock_meta.return_value = {
            "size_bytes": 1024,
            "content_type": "text/plain",
        }

        # Use actual model instances instead of MagicMocks to satisfy Pydantic serialization checks
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
            userid=None,
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
    with patch("app.apis.routes.upload_file.get_object_metadata") as mock_meta:
        mock_meta.side_effect = FileNotFoundError("Object not found in storage.")

        # Mock database query with actual model instance
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
            userid=None,
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
    with patch("app.apis.routes.upload_file.create_presigned_get_url") as mock_create_get:
        mock_create_get.return_value = {
            "view_url": "https://s3.example.com/uploads/123_test.txt?auth=abc",
            "key": "uploads/123_test.txt",
            "expires_in": 300,
        }

        response = client.post(
            "/files/view-url",
            json={"key": "uploads/123_test.txt"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["viewUrl"] == "https://s3.example.com/uploads/123_test.txt?auth=abc"
        assert data["key"] == "uploads/123_test.txt"


def test_get_view_url_route_not_found():
    with patch("app.apis.routes.upload_file.create_presigned_get_url") as mock_create_get:
        mock_create_get.side_effect = FileNotFoundError("File object with key 'missing' does not exist in storage.")

        response = client.post(
            "/files/view-url",
            json={"key": "uploads/missing.txt"},
        )

        assert response.status_code == 404
        assert "does not exist in storage" in response.json()["detail"]


def test_list_files_route_success():
    # Mock database query returning list of actual model instances
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
        userid=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_db_session.query().filter().order_by().all.return_value = [mock_file]

    response = client.get("/files")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["fileId"] == 42
    assert data[0]["title"] == "A Great Title"
    assert data[0]["tags"] == "tag1,tag2"


def test_update_metadata_route_success():
    # Mock database query with actual model instance
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
        userid=None,
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
