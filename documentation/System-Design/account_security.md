# Swan Drive — Account Security & Permanent Deletion Guide

> **Document Type:** System Architecture & Developer Guide  
> **Target Audience:** Developers, Technical Leads, and System Operators  
> **Status:** Production Reference  
> **Companion Document:** [`documentation/System-Design/auth_OTP.md`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/documentation/System-Design/auth_OTP.md)  
> **Hard Limit:** Max 500 lines

---

## 1. Overview & Core Philosophy

In a multi-service personal document platform like Swan Drive, a user's account does not live in a single database table. A single user owns:
* **Relational database rows** in MySQL (user record, file metadata, text chunks).
* **Document binaries** stored in object storage (AWS S3 or Backblaze B2).
* **Vector embeddings** stored across collections in Qdrant Cloud.
* **Transient session and rate-limiting keys** in Upstash Redis.

Because of this distributed architecture, **deleting an account is a high-risk, irreversible operation**. If an application deletes a database record first, it loses all references to the user's files and vector embeddings, leaving orphaned files in the cloud forever. 

This document explains how Swan Drive coordinates authentication, ownership, manual user deletion, and automatic 7-day inactivity cleanup safely and reliably across all four storage systems.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        SWAN DRIVE USER DATA FOOTPRINT                  │
├───────────────────────┬────────────────────────────────────────────────┤
│ AWS RDS MySQL 8       │ User credentials, file metadata, chunk texts   │
│ AWS S3 / Backblaze B2 │ Original file binaries (PDF, Word, CSV, etc.)  │
│ Qdrant Vector DB      │ High-dimensional search embeddings (768d)      │
│ Upstash Redis Cloud   │ Login rate counters, OTP stages, answer cache  │
└───────────────────────┴────────────────────────────────────────────────┘
```

---

## 2. Authentication, Ownership & Identity Protection

### 2.1 Authenticated Context (Zero Trust on Frontend)
Swan Drive enforces strict server-side identity derivation. When an API request arrives:
1. The backend extracts the `Authorization: Bearer <JWT>` header.
2. The JWT signature and expiration are verified using `SECRET_KEY` (see [`auth_OTP.md`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/documentation/System-Design/auth_OTP.md) for cryptographic details).
3. The subject claim (`sub`) is converted to an integer `user_id`.
4. The database verifies the user exists and has `status = "active"`.

> [!IMPORTANT]
> **Ownership Rule:** The frontend never sends `user_id` in deletion request payloads. Deletion operations are strictly derived from the authenticated token context (`current_user.id`). An attacker cannot delete someone else's account by guessing an ID.

---

## 3. Key Concepts Explained Simply

### 3.1 Permanent Deletion vs. Soft Deletion
* **Soft Deletion:** Hiding an account with a flag like `is_deleted = True`. The user's files, vectors, and database records remain stored on disk.
* **Permanent Deletion (Swan Drive):** Complete, unrecoverable removal. All MySQL rows, S3 files, Qdrant vectors, and Redis cache keys are physically erased. Once confirmed, **data cannot be recovered or restored**.

### 3.2 What is Idempotency?
In distributed computing, an operation is **idempotent** if running it multiple times produces the exact same result without causing errors or unwanted side effects.
* **Why it matters for deletion:** If the backend deletes a user's S3 files and Qdrant vectors, but a network blip causes the database step to fail, the deletion is retried. An idempotent deletion service recognizes that the S3 files are already gone, safely skips them, and completes the remaining steps cleanly.

### 3.3 Deletion State Machine (`active` ➔ `deleting` ➔ purged)
To prevent "ghost access" during a deletion operation:
1. The user's status is changed from `"active"` to `"deleting"` in MySQL as the very first step.
2. The authentication dependency (`get_current_user`) immediately blocks any further uploads, queries, or logins with `403 Forbidden`.
3. If the server restarts mid-deletion, the account remains safely locked until the cleanup completes.

---

## 4. Manual Deletion vs. Automatic Inactivity Cleanup

| Attribute | Manual Account Deletion | Automatic Inactivity Cleanup |
| :--- | :--- | :--- |
| **Trigger** | Explicit user action in frontend Settings page. | Background scheduled sweeper process. |
| **User Confirmation** | User must type exact phrase: `deleteme`. | None (automated policy after threshold). |
| **Eligibility** | Any authenticated user at any time. | 7 consecutive days (168h) without login. |
| **Inactivity Reference** | Not applicable. | `COALESCE(last_login_at, created_at) < 7 days`. |
| **Concurrency Guard** | User locked to `status = "deleting"`. | Upstash Redis distributed lock (`SET NX EX`). |
| **User Experience** | Immediate logout, storage purge, and redirect. | Transparent cleanup of abandoned accounts. |

---

## 5. Manual Account Deletion Flow

The manual account deletion workflow requires explicit user confirmation and guarantees complete multi-service cleanup:

```text
User in Frontend Settings
         │
         ▼
Types "deleteme" & Clicks Delete
         │
         ▼
[ DELETE /auth/me ] ──── Bearer JWT (Identity derived from token)
         │
         ▼
Validate confirmation == "deleteme" ─── Invalid ──► 400 Bad Request
         │ Valid
         ▼
Set user.status = "deleting" (Locks account immediately)
         │
         ▼
Fetch Inventory: Gather all s3_keys from MySQL file_metadata
         │
         ▼
Step 1: AWS S3 ─────────► Batch delete objects, versions & markers
         │
         ▼
Step 2: Qdrant Cloud ───► Delete vectors where user_id == target_id
         │
         ▼
Step 3: Upstash Redis ──► Evict rate limits, OTP keys & cached answers
         │
         ▼
Step 4: MySQL ──────────► db.delete(user) (Cascades file_metadata & chunks)
         │
         ▼
Return 200 OK ──────────► Frontend clears localStorage tokens and redirects
```

### Why the `deleteme` Safeguard Exists
Accidental clicks on irreversible operations can lead to catastrophic data loss. The confirmation input requires the user to type exactly `deleteme` (all lowercase, no spaces). The action button remains completely disabled until this exact string is entered.

---

## 6. Automatic Inactivity Deletion (The 7-Day Rule)

### 6.1 Last Login Tracking
To determine inactivity safely without guessing:
1. Every successful authentication (`POST /auth/login`, `/auth/login/form`, and `/auth/verify-otp`) updates the user's `last_login_at` timestamp.
2. For accounts that registered but never logged in again, their `created_at` timestamp serves as the fallback.
3. All calculations use UTC (`datetime.now(timezone.utc)`) to avoid daylight saving or timezone drift.

```text
Is Inactive? = (Current UTC Time - COALESCE(last_login_at, created_at)) >= 7 Days
```

### 6.2 Multi-Worker Safety & Distributed Locking
In production, Swan Drive runs Gunicorn with 2 Uvicorn worker processes (`-w 2`). If both workers run a background scheduler independently, they would attempt to delete the same expired accounts simultaneously.

Swan Drive uses a **distributed lock** in Upstash Redis to ensure only one worker executes the cleanup:

```text
Worker 1 (Gunicorn)                      Worker 2 (Gunicorn)
        │                                        │
        ├─► SET lock:cleanup NX EX 3600 ◄────────┤  (Both attempt to lock)
        │   (Acquired! Token: uuid-A)            │  (Lock exists! Skipped)
        ▼                                        ▼
Runs 7-day query & purges accounts       Continues serving user traffic
        │
        ▼
Release lock via Lua script
(Checks token == uuid-A before DEL)
```

1. **Unique Lock Token:** The acquiring worker generates a UUID.
2. **Safe Atomic Release:** The lock is released using a Lua script that verifies the token matches, preventing a worker from accidentally releasing another worker's refreshed lock.
3. **Automatic Expiration (TTL):** If a worker crashes while holding the lock, the lock automatically expires after 3,600 seconds, preventing deadlocks.

---

## 7. Storage Cleanup Across Services

### 7.1 Amazon S3 / Backblaze B2 Object Storage
* **The Challenge:** S3 buckets with versioning enabled do not permanently erase files on simple `delete_object` calls; they only insert a "Delete Marker". Incomplete multipart uploads also consume storage invisibly.
* **The Solution:**
  1. The cleanup service queries `list_object_versions` for the user's keys.
  2. It deletes both active object versions and delete markers in batches of up to 1,000 items.
  3. It inspects the `Errors` array in the response to verify that zero objects failed.

### 7.2 Qdrant Vector Cloud
* **The Challenge:** Qdrant stores document search embeddings. Dropping an entire collection would delete vectors belonging to other users.
* **The Solution:**
  Swan Drive collections (`document_vault` and `document_chunks_v1`) index `user_id` inside vector payloads. The deletion service executes a filtered deletion:
  ```python
  client.delete(
      collection_name=collection_name,
      points_selector=Filter(
          must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
      ),
      wait=True,
  )
  ```
  Only the targeted user's points are removed; other users' search embeddings remain untouched.

### 7.3 Upstash Redis Cloud
* **The Solution:** Swan Drive deletes only user-scoped keys:
  - `rate:login:{email}`
  - `otp:pending:{email}`
  - `otp:cooldown:{email}`
  - `rag:{user_id}:*`
  Global Redis flushes (`FLUSHDB`) are strictly prohibited.

### 7.4 AWS RDS MySQL Relational Database
* **The Solution:** The database uses InnoDB foreign keys configured with `ON DELETE CASCADE`:
  - When `db.delete(user)` is executed, MySQL automatically removes:
    - All rows in `file_metadata` where `userid == user.id`.
    - All rows in `document_chunks` where `user_id == user.id`.
    - The row in `user_corpus_state` where `user_id == user.id`.

---

## 8. Developer Safety & Smoke Testing Rules

> [!CAUTION]
> **NEVER TEST DELETION ON PRODUCTION OR REAL USER DATA.**
> Account deletion is permanent and cannot be undone.

When developing, verifying, or smoke-testing account deletion features:
1. **Synthetic Accounts Only:** Create dedicated test accounts (e.g., `test_delete_dev@swan.local`). Never test on personal or team accounts.
2. **Dry-Run Mode:** Always execute the deletion service with `dry_run=True` first. Verify the resource summary (number of files, chunks, S3 keys, and vector points) before executing real deletion.
3. **Cross-Tenant Verification:** Always inspect an adjacent user's documents before and after testing to ensure no shared resources were affected.
4. **Isolated Development Buckets:** In local development, ensure `S3_BUCKET_NAME` points to a dedicated sandbox or local emulator bucket.

---

## 9. Public Documentation & Privacy Guidelines

To protect application security and user privacy, all public documentation, logs, and commit messages must follow these rules:
* **Zero Secrets:** Never publish real API keys, passwords, bearer tokens, or database connection strings.
* **No Personal Data:** Never use real personal email addresses or usernames in examples. Use RFC-2606 safe domains like `user@example.com` or `user@swan.local`.
* **Generic Paths:** Use repository-relative paths (`backend/app/...`) instead of machine-specific paths (`/home/username/...`).
