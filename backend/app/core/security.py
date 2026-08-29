"""
backend/app/core/security.py

Security utilities for authentication.
Handles JWT token creation/decoding and Argon2id password hashing/verification.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Secret key used to sign JWT tokens (validated strictly via Pydantic Settings)
SECRET_KEY = settings.SECRET_KEY
# JWT signing algorithm
ALGORITHM = "HS256"
# Default token expiration time in minutes (15-30 minutes)
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing context using Argon2id
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against an Argon2id hash.

    Args:
        plain_password: The plain-text password to verify.
        hashed_password: The Argon2id hash stored in the database.

    Returns:
        True if the password matches the hash, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a plain-text password using Argon2id.

    Args:
        password: The plain-text password to hash.

    Returns:
        An Argon2id hashed version of the password.
    """
    return pwd_context.hash(password)


def create_access_token(*, user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token with the user ID as subject.

    Args:
        user_id: The integer primary key of the user.
        expires_delta: Optional custom expiration time. Defaults to 30 minutes.

    Returns:
        A signed JWT string containing 'sub' as str(user_id).
    """
    to_encode = {"sub": str(user_id)}
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt