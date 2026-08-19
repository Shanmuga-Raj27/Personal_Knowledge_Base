"""
backend/app/auth.py

Authentication dependencies for FastAPI.
Provides reusable functions to verify JWT tokens and fetch the current user.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.db_models import User
from app import schemas, security
from app.database import get_db

# Tells FastAPI where to find the token (for Swagger UI "Authorize" button)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_user(db: Session, username: str):
    """Fetch a single user from the database by their username.

    Args:
        db: SQLAlchemy database session.
        username: The username to search for.

    Returns:
        The User object if found, otherwise None.
    """
    return db.query(User).filter(User.username == username).first()


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    """FastAPI dependency that extracts and validates a JWT token.

    This function is called automatically by FastAPI on any route that
    lists it as a dependency. It decodes the token, verifies it, and
    returns the authenticated user.

    Args:
        token: The JWT token extracted from the Authorization header.
        db: Database session injected by FastAPI.

    Returns:
        The User object corresponding to the token.

    Raises:
        HTTPException: 401 if the token is missing, invalid, or the user does not exist.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Decode the JWT payload
        payload = jwt.decode(
            token, security.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user