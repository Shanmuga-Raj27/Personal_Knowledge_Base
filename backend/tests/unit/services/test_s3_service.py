import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
from app.services.AWS.s3_service import (
    create_presigned_put_url,
    check_object_exists,
    create_presigned_get_url,
    get_object_metadata,
)
from app.core.config import settings


def test_create_presigned_put_url_with_custom_endpoint():
    # Setup mock for boto3.client
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://s3.eu-central-003.backblazeb2.com/personal-knowledge-base/uploads/test.txt"

        # Explicitly configure the settings for the test
        original_endpoint = settings.AWS_ENDPOINT_URL
        settings.AWS_ENDPOINT_URL = "https://s3.eu-central-003.backblazeb2.com"

        try:
            result = create_presigned_put_url("test.txt", "text/plain")
            
            # Verify boto3.client was called with endpoint_url
            mock_boto_client.assert_called_once_with(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                endpoint_url="https://s3.eu-central-003.backblazeb2.com",
            )
            assert result["upload_url"] == "https://s3.eu-central-003.backblazeb2.com/personal-knowledge-base/uploads/test.txt"
            assert "key" in result
            assert result["expires_in"] == settings.S3_PRESIGNED_URL_EXPIRY
        finally:
            # Restore original settings
            settings.AWS_ENDPOINT_URL = original_endpoint

def test_create_presigned_put_url_invalid_mime():
    with pytest.raises(ValueError, match="Unsupported file type"):
        create_presigned_put_url("test.txt", "image/png")

def test_check_object_exists_success():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {"ContentLength": 1234}

        assert check_object_exists("uploads/valid.pdf") is True
        mock_s3.head_object.assert_called_once_with(
            Bucket=settings.S3_BUCKET_NAME,
            Key="uploads/valid.pdf",
        )

def test_check_object_exists_not_found():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
        mock_s3.head_object.side_effect = ClientError(error_response, "head_object")

        assert check_object_exists("uploads/missing.pdf") is False

def test_create_presigned_get_url_success():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {"ContentLength": 100}
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/uploads/doc.pdf?temp_auth=1"

        res = create_presigned_get_url("uploads/doc.pdf", expires_in=600)
        assert res["view_url"] == "https://s3.example.com/uploads/doc.pdf?temp_auth=1"
        assert res["key"] == "uploads/doc.pdf"
        assert res["expires_in"] == 600

def test_create_presigned_get_url_file_not_found():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
        mock_s3.head_object.side_effect = ClientError(error_response, "head_object")

        with pytest.raises(FileNotFoundError, match="does not exist in storage"):
            create_presigned_get_url("uploads/nonexistent.pdf")


def test_get_object_metadata_success():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {
            "ContentLength": 500,
            "ContentType": "text/markdown",
        }

        res = get_object_metadata("uploads/doc.md")
        assert res["size_bytes"] == 500
        assert res["content_type"] == "text/markdown"


def test_get_object_metadata_not_found():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
        mock_s3.head_object.side_effect = ClientError(error_response, "head_object")

        with pytest.raises(FileNotFoundError, match="does not exist in storage"):
            get_object_metadata("uploads/nonexistent.pdf")


