"""
backend/app/schemas/schemas.py

Pydantic schemas for user registration, authentication, and JWT token management.
"""
from datetime import datetime
import re
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

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_~`+\-=\[\]\\;/]", v):
            raise ValueError("Password must contain at least one special symbol")
        return v

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


class VerifyOtpRequest(BaseModel):
    """Schema for OTP verification request."""
    email: EmailStr = Field(..., max_length=255)
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")


class ResendOtpRequest(BaseModel):
    """Schema for requesting a new OTP."""
    email: EmailStr = Field(..., max_length=255)


class RegisterInitiateResponse(BaseModel):
    """Schema returned after pre-registration OTP email is dispatched."""
    message: str
    email: str
