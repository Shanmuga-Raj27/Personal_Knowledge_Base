"""
backend/app/schemas/schemas.py

Pydantic schemas for user registration, authentication, and JWT token management.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator


class UserBase(BaseModel):
    """Base user schema with shared fields."""
    email: EmailStr = Field(..., max_length=255)


class UserRegister(BaseModel):
    """Schema for user registration input."""
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(
        ..., min_length=8, description="Password must be at least 8 characters"
    )
    confirm_password: str = Field(..., min_length=8)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v


class UserLogin(BaseModel):
    """Schema for user login credentials."""
    email: EmailStr = Field(..., max_length=255)
    password: str = Field(...)


class UserOut(UserBase):
    """Public user profile schema returned on registration or user details endpoints."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    status: str
    created_at: datetime = Field(..., alias="createdAt")


class TokenData(BaseModel):
    """Schema for data encoded inside a JWT token payload."""
    user_id: Optional[int] = None


class Token(BaseModel):
    """Schema for the login response containing the JWT access token."""
    access_token: str
    token_type: str = "bearer"