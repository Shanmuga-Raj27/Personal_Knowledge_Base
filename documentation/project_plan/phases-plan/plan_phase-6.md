# Implementation Plan - Phase 6: Production-Oriented JWT Authentication & Secure Multi-User File Ownership

This document outlines the architecture, database schema changes, authentication endpoints, security middleware, multi-tenant data scoping, and database migration strategies for Phase 6 of the Personal Knowledge Base application.

---

## 1. Executive Summary & Goals

### High-Level Goal
> **Production-oriented JWT authentication and secure per-user database/file ownership for a small-scale multi-user application.**

The implementation prioritizes:
```text
Simple + Secure + Maintainable + Solo-Developer Friendly + Close to Production Practices
```

### Core Architecture & Refinement Summary
1. **`email` Column Width**: Defined as `VARCHAR(255)` in `users` model and Alembic migration.
2. **JWT Subject (`sub`)**: Uses the internal integer database **User ID** (`str(user.id)`) as the `sub` claim inside JWT tokens. Email is used strictly for database indexing and login credentials lookup.
3. **Password Hashing**: Uses **Argon2id** (`passlib[argon2]`). `users.hashed_password` column length is set to `VARCHAR(255)`.
4. **Short-Lived Access Tokens & Logout**: Simple 15–30 minute JWT access tokens. Client-side logout removes the stored access token. Since access tokens are short-lived, no server-side token revocation or blocklist is implemented in Phase 6.
5. **Basic Single-Instance Rate Limiting**: Implements simple in-memory attempt tracking for login requests (e.g. 5 failed logins per 15 mins per IP/email) to prevent brute-force attacks without introducing Redis.
6. **Safe Staged Migration for Orphan Files**: Unowned development/test records where `userid IS NULL` will be explicitly deleted in the Alembic migration script before altering `userid` to `nullable=False`.
7. **Upload Verification**: `/files/upload-complete` verifies that the uploaded object exists in S3/B2 storage before updating file status from `pending` to `active`.
8. **7-Step JWT Validation Pipeline**: Enforces full token validity checks before executing route handlers.
9. **Strict Multi-Tenant Scoping**: All protected file operations verify `FileMetadata.userid == current_user.id`.

---

## 2. High-Level Plan Structure

```text
Phase 6 Architecture

Database
 ├── User ownership
 ├── Constraints & schema normalization
 ├── Indexes (email, s3_key, userid)
 └── Alembic migration (safe staged deletion of unowned dev/test records)

Authentication
 ├── Register (email + password + confirm_password)
 ├── Login (email + password)
 ├── Argon2id password hashing
 ├── Short-lived JWT (15-30 mins, sub = user.id)
 └── Basic single-instance rate limiting

Authorization
 └── Strict scoping (userid == current_user.id)

File Security
 ├── Upload completion S3 verification
 ├── View presigned URL authorization
 ├── Update metadata authorization
 └── Delete file authorization

Testing
 ├── 7-step JWT validation tests (401/403 states)
 ├── Multi-tenant file ownership isolation tests
 └── Storage upload verification tests
```

---

## 3. Database Schema Specification

### A. `users` Table Schema

| Column | SQLAlchemy Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `Integer` | Primary Key, Index, Auto-Increment | Unique user identifier |
| `email` | `String(255)` | Unique, Index, `nullable=False` | Primary login identifier & contact email |
| `hashed_password` | `String(255)` | `nullable=False` | **Argon2id** hashed password |
| `status` | `String(20)` | `nullable=False`, Default: `"active"` | User account status (`active`, `disabled`) |
| `created_at` | `DateTime(timezone=True)` | `server_default=func.now()`, `nullable=False` | Account registration timestamp |

> [!NOTE]
> The `username` column from earlier prototypes is completely removed. `email` and `hashed_password` columns are allocated 255 characters each.

### B. `file_metadata` Table Upgrades

| Column | SQLAlchemy Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `fileid` | `Integer` | Primary Key, Index, Auto-Increment | File record unique identifier |
| `s3_key` | `String(255)` | Unique, Index, `nullable=False` | Object key in AWS S3 |
| `filename` | `String(255)` | `nullable=False` | Original file name |
| `content_type` | `String(100)` | `nullable=True` | File MIME type |
| `size_bytes` | `BigInteger` | `nullable=True` | File size in bytes |
| `status` | `String(20)` | `nullable=False`, Default: `"pending"` | Processing status (`pending`, `active`, `failed`) |
| `title` | `String(100)` | `nullable=True` | Custom document title (Max 100 chars) |
| `description` | `String(255)` | `nullable=True` | Document summary (Max 255 chars) |
| `tags` | `String(50)` | `nullable=True` | Comma-separated search tags (Max 50 chars) |
| `userid` | `Integer` | **`ForeignKey("users.id", ondelete="CASCADE")`**, **`nullable=False`** | Required owner link |
| `created_at` | `DateTime(timezone=True)` | `server_default=func.now()`, `nullable=False` | File record creation timestamp |
| `updated_at` | `DateTime(timezone=True)` | `server_default=func.now()`, `onupdate=func.now()`, `nullable=False` | Last modification timestamp |

---

## 4. Database Migration Strategy (Alembic)

Updating `file_metadata.userid` to `nullable=False` requires a safe, staged migration with minimal downtime:

### Alembic Migration Steps (`backend/alembic/versions/`)
1. **Identify & Delete Unowned Test Data**: Delete unreferenced development/test file records where `userid IS NULL`.
2. **Apply User Schema Changes**:
   - Drop `username` column and `ix_users_username` index from `users`.
   - Add `status` (`VARCHAR(20)`) and `created_at` (`DATETIME`) columns to `users`.
   - Expand `email` to `VARCHAR(255)` and `hashed_password` to `VARCHAR(255)`.
3. **Apply File Metadata Schema Upgrades**:
   - Alter `file_metadata.userid` to `NOT NULL` with `CASCADE` delete foreign key constraint.
   - Adjust column lengths for `title` (VARCHAR 100), `description` (VARCHAR 255), and `tags` (VARCHAR 50).

---

## 5. API Endpoints & Security Architecture

### A. JWT Access Tokens & Session Management
- **Token Expiry**: Short-lived (15–30 minutes).
- **Subject Claim**: Numeric User ID string:
  ```json
  {
    "sub": "123",
    "exp": 1756380000
  }
  ```
- **Logout Specification**: Client-side logout removes the stored access token. Since access tokens are short-lived, no server-side token revocation or blocklist is implemented in Phase 6.

---

### B. 7-Step JWT Validation Pipeline (`get_current_user`)

Every protected endpoint routes through FastAPI's `get_current_user` dependency, executing these checks sequentially:

```text
1. JWT exists in Authorization header ("Bearer <token>")  → else 401 Unauthorized
2. Signature is valid (decoded via SECRET_KEY & HS256)   → else 401 Unauthorized
3. Token is not expired ("exp" claim valid)               → else 401 Unauthorized
4. "sub" claim exists                                     → else 401 Unauthorized
5. "sub" is a valid integer string representation         → else 401 Unauthorized
6. User exists in database (query by user_id)            → else 401 Unauthorized
7. User status is active (user.status == "active")        → else 403 Forbidden
```

---

### C. Authentication Endpoints (`/auth`)

#### 1. Registration (`POST /auth/register`)
- **Request Body (`UserRegister`)**: `email`, `password`, `confirm_password`.
- **Validations**:
  - `email` is valid format (`EmailStr`).
  - `password` is at least 8 characters.
  - `password == confirm_password`.
  - Check database: return `400 Bad Request` if `email` is already registered.
- **Action**: Hash password using **Argon2id** (`passlib[argon2]`).
- **Response**: `201 Created` returning `UserOut` (`id`, `email`, `status`, `createdAt`).

#### 2. Login (`POST /auth/login`)
- **Abuse Protection**: Basic single-instance rate limiting (in-memory tracking per IP/email, e.g. 5 failed attempts per 15 minutes).
- **Request Body (`UserLogin`)**: `email`, `password`.
- **Validations**:
  - Query user by `email`. Verify Argon2id password hash.
  - Check account `user.status == "active"` (`403 Forbidden` if disabled).
- **Response**: `200 OK` returning access token with `"sub": str(user.id)`.

---

### D. Multi-Tenant Route Security (`/files`)

All protected file routes execute under `current_user: User = Depends(get_current_user)` and strictly enforce ownership checks (`FileMetadata.userid == current_user.id`):

| Route | Security Scoping & Action |
| :--- | :--- |
| `POST /files/upload-url` | Binds `userid = current_user.id` on pending file record creation |
| `POST /files/upload-complete` | Verifies file object actually exists in S3/B2 storage **and** asserts `s3_key == payload.key` AND `userid == current_user.id` |
| `POST /files/view-url` | Asserts `s3_key == payload.key` AND `userid == current_user.id` before issuing presigned GET URL |
| `GET /files` | Filters `status == 'active'` AND `userid == current_user.id` |
| `PATCH /files/{fileid}` | Filters `fileid == fileid` AND `userid == current_user.id` |
| `DELETE /files/{fileid}` | Filters `fileid == fileid` AND `userid == current_user.id` |

---

## 6. Explicit Exclusions (Out of Scope for Phase 6)

The following enterprise features are **intentionally excluded** to maintain a clean, maintainable solo-developer codebase:
- ❌ OAuth / Google / Social Login
- ❌ Email Verification & Password Reset Flows
- ❌ Refresh Tokens & Token Rotation Architectures
- ❌ Redis or External Caching / Rate-Limiting Services
- ❌ Microservices & Distributed Transactions
- ❌ Complex RBAC / Enterprise Audit-Log Infrastructure

---

## 7. Verification & Automated Testing Plan

### Expanded Pytest Integration Suite (`backend/tests/test_auth_and_files.py`)

```text
7-Step JWT Validation Tests:
- Request with No JWT token → 401 Unauthorized
- Request with Invalid JWT signature → 401 Unauthorized
- Request with Expired JWT token → 401 Unauthorized
- Request from Disabled user → 403 Forbidden

Multi-Tenant Scoping Tests:
- User A can view, update, download, and delete own files
- User B GET /files does NOT return User A's files
- User B PATCH /files/{user_a_fileid} returns 404 Not Found
- User B DELETE /files/{user_a_fileid} returns 404 Not Found
- User B POST /files/view-url for User A's file returns 404 Not Found

Upload Verification Tests:
- POST /files/upload-complete returns 404/error if object is missing in S3/B2
```

### Command Execution
```powershell
cd d:\Personal_Knowledge_Base\backend
pytest tests/test_auth_and_files.py -v
```
