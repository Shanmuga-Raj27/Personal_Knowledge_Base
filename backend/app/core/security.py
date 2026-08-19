"""
backend/app/security.py

Security utilities for authentication.
Handles JWT token creation/decoding and password hashing/verification.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()

# Secret key used to sign JWT tokens — must be kept private
SECRET_KEY = os.getenv("SECRET_KEY")
# JWT signing algorithm
ALGORITHM = "HS256"
# Default token expiration time in minutes
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Hash a plain-text password using bcrypt.

    Args:
        password: The plain-text password to hash.

    Returns:
        A bcrypt-hashed version of the password.
    """
    return pwd_context.hash(password)


def create_access_token(*, data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token.

    Args:
        data: Dictionary of claims to encode (e.g., {"sub": username}).
        expires_delta: Optional custom expiration time. Defaults to 15 minutes.

    Returns:
        A signed JWT string.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt