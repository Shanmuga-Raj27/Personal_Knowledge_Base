import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
import app.services.AWS.s3_service as s3_module
from app.services.AWS.s3_service import (
    create_presigned_put_url,
    check_object_exists,
    create_presigned_get_url,
    get_object_metadata,
    delete_s3_object,
    read_object_bytes_limited,
    async_read_object_bytes_limited,
)


from app.core.config import settings


@pytest.fixture(autouse=True)
def reset_s3_singleton():
    """Reset the S3 client singleton before and after each test."""
    s3_module._s3_client_instance = None
    yield
    s3_module._s3_client_instance = None


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


def test_delete_s3_object_success():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        delete_s3_object("uploads/valid.pdf")
        mock_s3.delete_object.assert_called_once_with(
            Bucket=settings.S3_BUCKET_NAME,
            Key="uploads/valid.pdf",
        )


def test_delete_s3_object_failure():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        error_response = {"Error": {"Code": "500", "Message": "Internal Error"}}
        mock_s3.delete_object.side_effect = ClientError(error_response, "delete_object")

        with pytest.raises(RuntimeError, match="Failed to delete S3 object"):
            delete_s3_object("uploads/file.pdf")


def test_read_object_bytes_limited_success():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {"ContentLength": 100}

        mock_body = MagicMock()
        mock_body.read.side_effect = [b"hello ", b"world", b""]
        mock_s3.get_object.return_value = {"Body": mock_body}

        data = read_object_bytes_limited("uploads/file.txt", max_bytes=1000)
        assert data == b"hello world"
        mock_s3.head_object.assert_called_once_with(
            Bucket=settings.S3_BUCKET_NAME,
            Key="uploads/file.txt",
        )
        mock_s3.get_object.assert_called_once_with(
            Bucket=settings.S3_BUCKET_NAME,
            Key="uploads/file.txt",
        )
        mock_body.close.assert_called_once()


def test_read_object_bytes_limited_file_not_found():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        error_response = {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}}
        mock_s3.head_object.side_effect = ClientError(error_response, "head_object")

        with pytest.raises(FileNotFoundError, match="File object with key 'uploads/missing.txt' does not exist"):
            read_object_bytes_limited("uploads/missing.txt", max_bytes=1000)


def test_read_object_bytes_limited_head_too_large():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {"ContentLength": 5000}

        with pytest.raises(ValueError, match="Object is too large: 5000 bytes"):
            read_object_bytes_limited("uploads/huge.pdf", max_bytes=1000)

        mock_s3.get_object.assert_not_called()


def test_read_object_bytes_limited_stream_exceeds_max_bytes():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        # Head object says 500 bytes (under 1000 limit)
        mock_s3.head_object.return_value = {"ContentLength": 500}

        mock_body = MagicMock()
        # Stream unexpectedly returns 600 + 600 = 1200 bytes (> 1000 limit)
        mock_body.read.side_effect = [b"a" * 600, b"b" * 600]
        mock_s3.get_object.return_value = {"Body": mock_body}

        with pytest.raises(ValueError, match="Object exceeded max read size: 1000 bytes"):
            read_object_bytes_limited("uploads/expanding.pdf", max_bytes=1000)

        mock_body.close.assert_called_once()


def test_read_object_bytes_limited_client_error():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        error_response = {"Error": {"Code": "InternalError", "Message": "Internal Error"}}
        mock_s3.head_object.side_effect = ClientError(error_response, "head_object")

        with pytest.raises(RuntimeError, match="Failed to read object bytes from storage"):
            read_object_bytes_limited("uploads/file.pdf", max_bytes=1000)


@pytest.mark.anyio
async def test_async_read_object_bytes_limited():
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.head_object.return_value = {"ContentLength": 50}

        mock_body = MagicMock()
        mock_body.read.side_effect = [b"async content", b""]
        mock_s3.get_object.return_value = {"Body": mock_body}

        res = await async_read_object_bytes_limited("uploads/async.txt", max_bytes=100)
        assert res == b"async content"
        mock_body.close.assert_called_once()





