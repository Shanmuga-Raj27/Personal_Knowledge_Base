"""
backend/app/auth/auth.py

Authentication dependencies for FastAPI.
Provides reusable functions to verify JWT tokens and fetch the current user.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database.db_models import User
from app.schemas.schemas import TokenData
from app.core import security
from app.database import get_db

# Tells FastAPI where to find the token (for Swagger UI "Authorize" button)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Fetch a single user from the database by their email address.

    Args:
        db: SQLAlchemy database session.
        email: The email address to search for.

    Returns:
        The User object if found, otherwise None.
    """
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Fetch a single user from the database by their numeric user ID.

    Args:
        db: SQLAlchemy database session.
        user_id: The integer primary key ID to search for.

    Returns:
        The User object if found, otherwise None.
    """
    return db.query(User).filter(User.id == user_id).first()


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """FastAPI dependency enforcing the 7-Step JWT validation pipeline:
    1. JWT exists (handled by oauth2_scheme)
    2. Signature valid
    3. Token not expired
    4. 'sub' claim exists
    5. 'sub' is a valid integer user ID
    6. User exists in database
    7. User status is active (returns 403 if disabled)

    Args:
        token: The JWT token extracted from the Authorization header.
        db: Database session injected by FastAPI.

    Returns:
        The authenticated User object.

    Raises:
        HTTPException 401: If token is missing, invalid, expired, or user not found.
        HTTPException 403: If user account is disabled.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Step 2 & 3: Decode JWT payload (verifies signature and expiration)
        payload = jwt.decode(
            token, security.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        # Step 4: Extract 'sub' claim
        sub: Optional[str] = payload.get("sub")
        if sub is None:
            raise credentials_exception

        # Step 5: Convert 'sub' to integer user ID
        try:
            user_id = int(sub)
        except (ValueError, TypeError):
            raise credentials_exception

        token_data = TokenData(user_id=user_id)
    except JWTError:
        raise credentials_exception

    # Step 6: User exists in database
    user = get_user_by_id(db, user_id=token_data.user_id)
    if user is None:
        raise credentials_exception

    # Step 7: Check user status is active
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user