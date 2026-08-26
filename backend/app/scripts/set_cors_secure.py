"""
backend/app/scripts/set_cors_secure.py

One-time administrative script to apply a secure, highly restrictive CORS configuration
to the Backblaze B2 S3 bucket, whitelisting ONLY the local frontend development origin
and restricting operations solely to PUT (file uploads).
"""
import sys
import os

# Append project root to sys.path to allow imports from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import boto3
from app.core.config import settings


def apply_secure_cors():
    print("Connecting to Backblaze B2 S3 compatibility endpoint...")
    s3 = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        endpoint_url=settings.AWS_ENDPOINT_URL,
    )

    cors_configuration = {
        "CORSRules": [
            {
                "AllowedHeaders": ["content-type"],
                "AllowedMethods": ["PUT"],  # ONLY allow file uploading
                "AllowedOrigins": ["http://localhost:5173"],  # ONLY allow local React development port
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3600,
            }
        ]
    }

    print(f"Applying secure CORS configuration to bucket: {settings.S3_BUCKET_NAME}...")
    try:
        s3.put_bucket_cors(
            Bucket=settings.S3_BUCKET_NAME,
            CORSConfiguration=cors_configuration,
        )
        print("CORS rules updated successfully on Backblaze B2!")
    except Exception as exc:
        print(f"Error applying CORS rules: {exc}", file=sys.stderr)


if __name__ == "__main__":
    apply_secure_cors()
