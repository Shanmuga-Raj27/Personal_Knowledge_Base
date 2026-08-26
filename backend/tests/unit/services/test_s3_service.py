import pytest
from unittest.mock import patch, MagicMock
from app.services.AWS.s3_service import create_presigned_put_url
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
