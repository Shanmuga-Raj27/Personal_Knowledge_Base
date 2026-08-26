import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


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


def test_complete_upload_route_success():
    with patch("app.apis.routes.upload_file.check_object_exists") as mock_check:
        mock_check.return_value = True

        response = client.post(
            "/files/upload-complete",
            json={"key": "uploads/123_test.txt", "filename": "test.txt"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert data["key"] == "uploads/123_test.txt"
        assert "verified successfully" in data["message"]


def test_complete_upload_route_not_found():
    with patch("app.apis.routes.upload_file.check_object_exists") as mock_check:
        mock_check.return_value = False

        response = client.post(
            "/files/upload-complete",
            json={"key": "uploads/missing.txt"},
        )

        assert response.status_code == 404
        assert "Object not found in storage" in response.json()["detail"]


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
