"""
backend/app/apis/routes/auth_routes.py

Authentication router for user registration, OTP verification, and login.
Features:
- Ephemeral pre-registration using Upstash Redis Cloud (10-minute TTL)
- Synchronous Resend API email delivery with strict failure propagation
- Atomic OTP verification via Redis Lua script (concurrency & attempt limit guard)
- Distributed Redis rate limiting for failed login attempts
- Argon2id password hashing & JWT bearer token issuance
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core import security
from app.database import get_db
from app.database.db_models import User
from app.schemas.schemas import (
    RegisterInitiateResponse,
    ResendOtpRequest,
    Token,
    UserLogin,
    UserRegister,
    VerifyOtpRequest,
)
from app.auth.auth_dependencies import get_user_by_email
from app.services.cache.redis_cache import get_redis_client
from app.services.email.resend_service import send_otp_email, ResendDeliveryError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Atomic Lua script for OTP verification, rate tracking, and single-use consumption.
# Returns a JSON-encoded string to avoid Redis/Upstash data structure translation issues.
VERIFY_OTP_LUA = """
local raw = redis.call('GET', KEYS[1])
if not raw then
    return cjson.encode({status = "NOT_FOUND"})
end
local data = cjson.decode(raw)
if data.attempts >= 5 then
    redis.call('DEL', KEYS[1])
    return cjson.encode({status = "LOCKED"})
end
if data.otp_hash ~= ARGV[1] then
    data.attempts = data.attempts + 1
    if data.attempts >= 5 then
        redis.call('DEL', KEYS[1])
        return cjson.encode({status = "LOCKED"})
    else
        local ttl = redis.call('TTL', KEYS[1])
        if ttl > 0 then
            redis.call('SETEX', KEYS[1], ttl, cjson.encode(data))
        end
        return cjson.encode({status = "MISMATCH", attempts = data.attempts})
    end
end
-- Success: Atomically consume key
redis.call('DEL', KEYS[1])
return cjson.encode({status = "OK", hashed_password = data.hashed_password})
"""


async def check_login_rate_limit(email: str) -> None:
    """Enforce distributed Redis rate limiting for failed login attempts (max 5 per 15 minutes)."""
    try:
        redis = get_redis_client()
        key = f"rate:login:{email.lower()}"
        current_val = await redis.get(key)
        if current_val and int(current_val) >= 5:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please try again in 15 minutes.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Redis rate limit check failed, allowing request (fail-open): %s", exc)


async def record_failed_login(email: str) -> None:
    """Increment failed login attempts counter in Redis with 15-minute expiration."""
    try:
        redis = get_redis_client()
        key = f"rate:login:{email.lower()}"
        attempts = await redis.incr(key)
        if attempts == 1:
            await redis.execute_command("EXPIRE", key, 900)
    except Exception as exc:
        logger.warning("Failed to record failed login in Redis: %s", exc)


async def clear_failed_login(email: str) -> None:
    """Clear failed login attempts counter in Redis on successful authentication."""
    try:
        redis = get_redis_client()
        key = f"rate:login:{email.lower()}"
        await redis.delete(key)
    except Exception as exc:
        logger.warning("Failed to clear failed login in Redis: %s", exc)


@router.post("/register", response_model=RegisterInitiateResponse, status_code=status.HTTP_200_OK)
async def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    """Initiate registration by validating credentials and emailing a 6-digit OTP.

    Does NOT create a MySQL user row. Stores pending registration in Upstash Redis
    with a 10-minute TTL. Enforces a 60-second resend cooldown.
    """
    clean_email = payload.email.lower().strip()

    # 1. Check if email is already registered in MySQL
    existing_user = get_user_by_email(db, email=clean_email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address is already registered.",
        )

    redis = get_redis_client()

    # 2. Check 60-second cooldown
    cooldown = await redis.get(f"otp:cooldown:{clean_email}")
    if cooldown:
        ttl = await redis.ttl(f"otp:cooldown:{clean_email}")
        wait_seconds = ttl if ttl > 0 else 60
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {wait_seconds} seconds before requesting another code.",
        )

    # 3. Cryptographic preparation: OTP + HMAC-SHA256 + Argon2id
    otp_code = security.generate_otp()
    otp_hmac = security.compute_otp_hmac(otp_code)
    hashed_pw = security.get_password_hash(payload.password)

    # 4. Synchronous email delivery via Resend API
    # Must precede Redis staging so failed sends never report success to the user
    try:
        await send_otp_email(to_email=clean_email, otp_code=otp_code)
    except ResendDeliveryError as exc:
        logger.error("Failed to deliver registration OTP to %s: %s", clean_email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to deliver verification email. Please check your email address or try again.",
        ) from exc

    # 5. Store pending registration payload in Upstash Redis (10 minutes TTL)
    pending_payload = {
        "hashed_password": hashed_pw,
        "otp_hash": otp_hmac,
        "attempts": 0,
    }
    await redis.setex(
        f"otp:pending:{clean_email}",
        600,
        json.dumps(pending_payload),
    )

    # 6. Set 60-second cooldown in Redis
    await redis.setex(f"otp:cooldown:{clean_email}", 60, "1")

    return RegisterInitiateResponse(
        message="Verification code sent to your email. Please verify within 10 minutes.",
        email=clean_email,
    )


@router.post("/verify-otp", response_model=Token, status_code=status.HTTP_200_OK)
async def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    """Verify submitted 6-digit OTP atomically and activate user account in MySQL.

    Uses an atomic Redis Lua script to prevent concurrent double-consumption and
    strictly invalidate the OTP after 5 incorrect attempts.
    On success, creates MySQL user record and issues JWT access token.
    """
    clean_email = payload.email.lower().strip()
    submitted_hmac = security.compute_otp_hmac(payload.otp)

    redis = get_redis_client()
    key = f"otp:pending:{clean_email}"

    # Execute atomic Lua evaluation
    try:
        raw_result = await redis.eval(VERIFY_OTP_LUA, 1, key, submitted_hmac)
        result = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except Exception as exc:
        logger.error("Error evaluating OTP verification Lua script: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification service encountered an internal error. Please try again.",
        ) from exc

    res_status = result.get("status")

    if res_status == "NOT_FOUND":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired or is invalid. Please register again.",
        )

    if res_status == "LOCKED":
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect attempts. This code has been invalidated. Please request a new code.",
        )

    if res_status == "MISMATCH":
        attempts = result.get("attempts", 1)
        remaining = max(0, 5 - attempts)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid verification code. {remaining} attempt(s) remaining.",
        )

    if res_status != "OK" or "hashed_password" not in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not verify OTP. Please try again.",
        )

    # Concurrency safe: Only the single atomic consumer reaches this block
    # Check duplicate in MySQL (defence-in-depth)
    existing_user = get_user_by_email(db, email=clean_email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address is already registered.",
        )

    now_utc = datetime.now(timezone.utc)
    new_user = User(
        email=clean_email,
        hashed_password=result["hashed_password"],
        status="active",
        created_at=now_utc,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    if not new_user.created_at:
        new_user.created_at = now_utc

    # Clean up cooldown key as user is now active
    await redis.delete(f"otp:cooldown:{clean_email}")

    # Issue JWT token for immediate authenticated session
    access_token = security.create_access_token(user_id=new_user.id, email=new_user.email)
    return Token(access_token=access_token, token_type="bearer")


@router.post("/resend-otp", status_code=status.HTTP_200_OK)
async def resend_otp(payload: ResendOtpRequest):
    """Resend a new 6-digit OTP for an existing pending registration.

    Enforces 60-second cooldown and resets the 5-attempt budget with a refreshed 10m TTL.
    """
    clean_email = payload.email.lower().strip()
    redis = get_redis_client()

    # 1. Enforce 60-second cooldown
    cooldown = await redis.get(f"otp:cooldown:{clean_email}")
    if cooldown:
        ttl = await redis.ttl(f"otp:cooldown:{clean_email}")
        wait_seconds = ttl if ttl > 0 else 60
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {wait_seconds} seconds before requesting another code.",
        )

    # 2. Verify pending registration exists
    raw_pending = await redis.get(f"otp:pending:{clean_email}")
    if not raw_pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending registration found for this email address. Please register first.",
        )

    try:
        pending_data = json.loads(raw_pending)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pending registration state. Please register again.",
        )

    # 3. Generate new OTP and HMAC
    otp_code = security.generate_otp()
    otp_hmac = security.compute_otp_hmac(otp_code)

    # 4. Deliver email via Resend
    try:
        await send_otp_email(to_email=clean_email, otp_code=otp_code)
    except ResendDeliveryError as exc:
        logger.error("Failed to resend OTP to %s: %s", clean_email, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to deliver verification email. Please try again later.",
        ) from exc

    # 5. Refresh pending payload with new hash, reset attempts, and restart 10-minute TTL
    pending_data["otp_hash"] = otp_hmac
    pending_data["attempts"] = 0
    await redis.setex(
        f"otp:pending:{clean_email}",
        600,
        json.dumps(pending_data),
    )

    # 6. Set 60-second cooldown
    await redis.setex(f"otp:cooldown:{clean_email}", 60, "1")

    return {"message": "A new verification code has been sent to your email."}


@router.post("/login", response_model=Token)
async def login_user(
    payload: UserLogin,
    db: Session = Depends(get_db),
):
    """Authenticate user credentials and issue a short-lived JWT access token."""
    clean_email = payload.email.lower().strip()

    # Distributed Redis rate limit check
    await check_login_rate_limit(clean_email)

    user = get_user_by_email(db, email=clean_email)
    if not user or not security.verify_password(
        payload.password, user.hashed_password
    ):
        await record_failed_login(clean_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check account status
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Clear rate limit counter on successful login
    await clear_failed_login(clean_email)

    # Issue JWT access token with user.id as 'sub' and email for frontend rehydration
    access_token = security.create_access_token(user_id=user.id, email=user.email)
    return Token(access_token=access_token, token_type="bearer")


@router.post("/login/form", response_model=Token, include_in_schema=False)
async def login_user_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Form endpoint supporting Swagger UI 'Authorize' button."""
    clean_email = form_data.username.lower().strip()

    await check_login_rate_limit(clean_email)

    user = get_user_by_email(db, email=clean_email)
    if not user or not security.verify_password(
        form_data.password, user.hashed_password
    ):
        await record_failed_login(clean_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    await clear_failed_login(clean_email)
    access_token = security.create_access_token(user_id=user.id, email=user.email)
    return Token(access_token=access_token, token_type="bearer")
