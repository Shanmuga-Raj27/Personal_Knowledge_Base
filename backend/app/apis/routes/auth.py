"""
backend/app/apis/routes/auth.py

Authentication router for user registration and login with basic single-instance rate limiting.
"""
import time
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core import security
from app.database import get_db
from app.database.db_models import User
from app.schemas.schemas import Token, UserLogin, UserOut, UserRegister
from app.auth.auth import get_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])

# Basic single-instance in-memory rate limiter for login attempts
# Format: { (ip, email): [(timestamp1), (timestamp2), ...] }
LOGIN_ATTEMPTS: Dict[Tuple[str, str], list[float]] = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 900  # 15 minutes


def check_rate_limit(client_ip: str, email: str) -> None:
    """Enforce basic single-instance rate limiting for failed login attempts.

    Args:
        client_ip: Client IP address from request.
        email: Target login email address.

    Raises:
        HTTPException 429: If failed attempts exceed MAX_LOGIN_ATTEMPTS within 15 minutes.
    """
    key = (client_ip, email.lower())
    now = time.time()
    # Filter attempts within the 15-minute window
    LOGIN_ATTEMPTS[key] = [
        t for t in LOGIN_ATTEMPTS[key] if now - t < RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(LOGIN_ATTEMPTS[key]) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again in 15 minutes.",
        )


def record_failed_attempt(client_ip: str, email: str) -> None:
    """Record a failed login attempt for rate limiting.

    Args:
        client_ip: Client IP address.
        email: Target login email.
    """
    key = (client_ip, email.lower())
    LOGIN_ATTEMPTS[key].append(time.time())


def clear_failed_attempts(client_ip: str, email: str) -> None:
    """Clear failed login attempts after a successful authentication.

    Args:
        client_ip: Client IP address.
        email: Target login email.
    """
    key = (client_ip, email.lower())
    if key in LOGIN_ATTEMPTS:
        del LOGIN_ATTEMPTS[key]


@router.post(
    "/register", response_model=UserOut, status_code=status.HTTP_201_CREATED
)
async def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    """Register a new user account with email and password.

    Validates password confirmation, checks for duplicate emails, and stores an Argon2id hash.
    """
    # Check if email is already registered
    existing_user = get_user_by_email(db, email=payload.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address is already registered.",
        )

    # Hash password using Argon2id
    hashed_pw = security.get_password_hash(payload.password)

    # Insert new user record
    now_utc = datetime.now(timezone.utc)
    new_user = User(
        email=payload.email.lower(),
        hashed_password=hashed_pw,
        status="active",
        created_at=now_utc,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    if not new_user.created_at:
        new_user.created_at = now_utc

    return new_user


@router.post("/login", response_model=Token)
async def login_user(
    request: Request,
    payload: UserLogin,
    db: Session = Depends(get_db),
):
    """Authenticate user credentials and issue a short-lived JWT access token."""
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Rate limiting check
    check_rate_limit(client_ip, payload.email)

    user = get_user_by_email(db, email=payload.email.lower())
    if not user or not security.verify_password(
        payload.password, user.hashed_password
    ):
        record_failed_attempt(client_ip, payload.email)
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
    clear_failed_attempts(client_ip, payload.email)

    # Issue JWT access token with user.id as numeric 'sub' claim
    access_token = security.create_access_token(user_id=user.id)
    return Token(access_token=access_token, token_type="bearer")


@router.post("/login/form", response_model=Token, include_in_schema=False)
async def login_user_form(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Form endpoint supporting Swagger UI 'Authorize' button."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    email = form_data.username  # OAuth2 form uses 'username' field for email

    check_rate_limit(client_ip, email)

    user = get_user_by_email(db, email=email.lower())
    if not user or not security.verify_password(
        form_data.password, user.hashed_password
    ):
        record_failed_attempt(client_ip, email)
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

    clear_failed_attempts(client_ip, email)
    access_token = security.create_access_token(user_id=user.id)
    return Token(access_token=access_token, token_type="bearer")
