"""
backend/app/schemas.py

Pydantic schemas for request and response validation.
These define the "shape" of data entering and leaving the API.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional


class UserBase(BaseModel):
    """Base user schema with shared fields."""
    email: EmailStr
    username: str


class UserIn(UserBase):
    """Schema for user registration input.

    Includes password with a minimum length requirement.
    """
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")


class UserInDBBase(UserBase):
    """Base schema for user data stored in the database.

    Includes the `id` field. Configures Pydantic to read from ORM attributes.
    """
    id: int

    class Config:
        from_attributes = True


class UserInDB(UserInDBBase):
    """Full user schema including the hashed password.

    Never return this schema to the client — it contains sensitive data.
    """
    hashed_password: str


class TokenData(BaseModel):
    """Schema for data encoded inside a JWT token."""
    username: Optional[str] = None


class Token(BaseModel):
    """Schema for the login response containing the access token."""
    access_token: str
    token_type: str