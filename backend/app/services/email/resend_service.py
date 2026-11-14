"""
backend/app/services/email/resend_service.py

Lightweight transactional email service using Resend REST API via httpx.
Handles verification OTP email delivery with clean HTML formatting and explicit error handling.
"""
import logging
from typing import Any, Dict

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class ResendDeliveryError(Exception):
    """Raised when Resend API fails to deliver an email."""
    pass


async def send_otp_email(to_email: str, otp_code: str) -> Dict[str, Any]:
    """Send a 6-digit verification code to the target email address via Resend REST API.

    Args:
        to_email: Recipient email address.
        otp_code: 6-digit numeric verification OTP.

    Returns:
        Dict containing Resend API response JSON (e.g. {"id": "..."}).

    Raises:
        ResendDeliveryError: If API key is missing or Resend API returns an error status.
    """
    if not settings.RESEND_API_KEY:
        logger.error("Cannot send verification email: RESEND_API_KEY is not configured.")
        raise ResendDeliveryError("Email delivery service is not configured (missing RESEND_API_KEY).")

    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 560px; margin: 0 auto; padding: 32px 24px; border: 1px solid #eaeaea; border-radius: 12px; background-color: #ffffff;">
        <div style="margin-bottom: 24px; text-align: center;">
            <h1 style="color: #111827; font-size: 24px; font-weight: 700; margin: 0 0 8px;">Swan Drive</h1>
            <p style="color: #6b7280; font-size: 14px; margin: 0;">Personal Knowledge Base & Document Vault</p>
        </div>
        <div style="padding: 24px; background-color: #f9fafb; border-radius: 8px; text-align: center; margin-bottom: 24px;">
            <p style="color: #374151; font-size: 14px; margin: 0 0 12px;">Your verification code is:</p>
            <div style="display: inline-block; font-size: 36px; font-weight: 800; letter-spacing: 6px; color: #FF6B00; padding: 12px 24px; background: #ffffff; border: 1px dashed #FF6B00; border-radius: 8px;">
                {otp_code}
            </div>
            <p style="color: #6b7280; font-size: 12px; margin: 12px 0 0;">This code is single-use and will expire in <strong>10 minutes</strong>.</p>
        </div>
        <p style="color: #4b5563; font-size: 13px; line-height: 1.5; margin: 0 0 16px;">
            Please enter this code on the verification screen to activate your account. If you did not sign up for Swan Drive, you can safely ignore this email.
        </p>
        <hr style="border: none; border-top: 1px solid #f3f4f6; margin: 24px 0;" />
        <p style="color: #9ca3af; font-size: 11px; text-align: center; margin: 0;">
            Swan Drive Security &bull; This is an automated message, please do not reply.
        </p>
    </div>
    """

    payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": f"Your Swan Drive Verification Code: {otp_code}",
        "html": html_body,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(RESEND_API_URL, headers=headers, json=payload)
            if response.status_code >= 400:
                logger.error(
                    "Resend API error [%d]: %s", response.status_code, response.text
                )
                raise ResendDeliveryError(
                    f"Resend API error ({response.status_code}): {response.text}"
                )
            return response.json()
    except httpx.RequestError as exc:
        logger.error("Resend HTTP request failed: %s", str(exc))
        raise ResendDeliveryError(f"Email delivery network error: {str(exc)}") from exc
