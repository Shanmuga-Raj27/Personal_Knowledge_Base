# Swan Drive: OTP Email Verification & Authentication

> **Document Type:** System Architecture & Technical Guide  
> **Target Audience:** Developers, Technical Leads, and System Architects  
> **Status:** Production Reference  

---

## 1. Overview & Problem Statement

In standard authentication workflows, registration endpoints often write user accounts directly to a database with `status = "active"`. This introduces several production challenges:

* **Fake & Typo Accounts:** Users mistype or submit throwaway email addresses. These records permanently clutter database tables and consume unique email indexes.
* **Database & Resource Pollution:** Unverified accounts can accumulate over time, requiring complex background cleanup routines or manual database pruning.
* **Unconfirmed Ownership:** Without proving ownership before account activation, applications cannot guarantee delivery of future password resets or security alerts.

### The Swan Drive Solution
Swan Drive uses an **ephemeral pre-registration model** combining **Upstash Redis Cloud** and **Resend API**:
1. When a user registers, their account is **not** written to MySQL.
2. The registration payload is staged temporarily in Redis with a 10-minute automatic expiration (TTL).
3. A 6-digit One-Time Password (OTP) is generated, HMAC-hashed, and emailed via Resend.
4. Only upon entering the correct OTP is the account permanently written to MySQL and a JSON Web Token (JWT) issued.

---

## 2. Component Roles & Storage Boundaries

Data and cryptography are strictly segregated across clear boundaries:

| Layer | Engine | Lifespan | Protection | Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| **Pending Registration** | Upstash Redis | 10 Minutes (600s TTL) | Argon2id + HMAC-SHA256 | Holds unverified registration state safely outside MySQL. |
| **Resend Cooldown** | Upstash Redis | 60 Seconds (60s TTL) | String flag (`"1"`) | Throttles email delivery to prevent inbox flooding. |
| **Attempt Tracking** | Upstash Redis | Tied to pending record | Atomic integer counter | Enforces a hard limit of 5 verification attempts. |
| **Permanent Account** | AWS RDS MySQL 8 | Indefinite | Argon2id password hash | Stores verified user records (`status = 'active'`). |
| **API Authorization** | Client Headers | 30 Minutes | JWT with HS256 signature | Authenticates requests across protected document routes. |

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        CRYPTOGRAPHIC SEPARATION                        │
├───────────────────────┬────────────────────────────────────────────────┤
│ User Password         │ Argon2id (Memory-hard password hashing)        │
│ One-Time Password     │ HMAC-SHA256 (Server-keyed cryptographic hash)  │
│ API Bearer Token      │ JWT (HS256 signature with SECRET_KEY)          │
└───────────────────────┴────────────────────────────────────────────────┘
```

---

## 3. End-to-End Authentication Flows

### Flow 1: User Registration (`POST /auth/register`)

```text
User Submits Email & Password
             │
             ▼
     Duplicate Email? ─── Yes ──► 400 Bad Request
             │ No
             ▼
     Cooldown Active? ─── Yes ──► 429 Too Many Requests (Wait Xs)
             │ No
             ▼
Generate 6-digit OTP & Hash Password (Argon2id)
             │
             ▼
     Send Email via Resend ─── Failed ──► 502 Bad Gateway (Registration aborted)
             │ Succeeded
             ▼
Store in Redis: otp:pending:{email} (TTL: 10m)
Set Cooldown:   otp:cooldown:{email} (TTL: 60s)
             │
             ▼
Return 200 OK (Zero MySQL rows created)
```

1. **Duplicate Check:** Verifies the email is not already registered in MySQL.
2. **Cooldown Check:** Verifies no active 60-second cooldown exists in Redis for this email.
3. **Password & OTP Processing:** Hashes the password with Argon2id and generates a secure 6-digit OTP.
4. **Synchronous Email Dispatch:** Delivers the verification code via Resend API. If delivery fails (e.g., network error or provider rejection), the request aborts with `502 Bad Gateway` and nothing is stored in Redis.
5. **Redis Staging:** Stores the Argon2id hash, HMAC OTP hash, and attempt counter (`0`) in Redis with a 600-second TTL.
6. **Result:** The user is informed to verify their email. **No rows exist in MySQL.**

---

### Flow 2: OTP Verification (`POST /auth/verify-otp`)

```text
User Submits 6-digit Code
             │
             ▼
Execute Atomic Redis Lua Script:
  ├── Key Missing / Expired? ──► 400 Bad Request
  ├── Already >= 5 attempts? ──► Delete key & return 429
  ├── Code Incorrect? ─────────► Increment attempts (Delete key if 5th) -> 400 Bad Request
  └── Code Correct? ───────────► Atomically delete key & return payload
             │
             ▼
Insert User into MySQL (status: 'active')
Issue JWT Access Token
             │
             ▼
Return 200 OK with Bearer Token (User logged in)
```

1. **HMAC Calculation:** The server hashes the submitted 6-digit code using HMAC-SHA256 with the server's secret key.
2. **Atomic Lua Execution:** A single Redis Lua script checks attempts, compares the hash, and consumes the key atomically.
3. **5-Attempt Lockout:** If an incorrect code is entered 5 times, the key is permanently deleted immediately to block brute-force attacks.
4. **Account Creation:** Upon successful verification, the user record is inserted into MySQL with `status = "active"`.
5. **Token Issuance:** A signed JWT access token is minted and returned, authenticating the user immediately without requiring a separate login step.

---

### Flow 3: Resending OTP (`POST /auth/resend-otp`)

```text
User Requests New Code
             │
             ▼
Cooldown Active (< 60s)? ─── Yes ──► 429 Too Many Requests
             │ No
             ▼
Pending Key in Redis? ─────── No ──► 400 Bad Request (Please register again)
             │ Yes
             ▼
Generate New OTP & New HMAC Hash
Send Email via Resend ─────── Failed ──► 502 Bad Gateway
             │ Succeeded
             ▼
Update Redis: Refresh TTL to 10m, Reset attempts to 0
Set Cooldown: 60s
             │
             ▼
Return 200 OK
```

1. **Cooldown Guard:** Prevents requesting a new code if less than 60 seconds have passed.
2. **Existence Check:** Ensures an unexpired pending registration exists in Redis.
3. **Refreshed Security:** Generates a new OTP, resets attempts to `0`, and refreshes the 10-minute TTL.

---

## 4. Deep Dive: Core Technologies & Concepts

### Upstash Redis & Time-To-Live (TTL)
Temporary registration state belongs in Redis rather than a relational database:
* **Automatic Garbage Collection:** Keys expire automatically when their TTL expires. Abandoned registrations vanish without cron jobs or database cleanup scripts.
* **Atomic Memory Speed:** Operations like `INCR`, `SETEX`, and Lua scripts execute in sub-millisecond memory time.
* **Serverless HTTP REST:** Upstash Redis is queried over HTTPS via `httpx`. This avoids persistent TCP connection pools on the backend, preserving the small memory footprint of cloud instances.

### Redis Key Schema
* `otp:pending:{email}` — Holds `{hashed_password, otp_hash, attempts}` with a 600-second (10-minute) TTL.
* `otp:cooldown:{email}` — Holds `"1"` with a 60-second TTL to throttle resends.
* `rate:login:{email}` — Holds integer failed login attempts with a 900-second (15-minute) TTL.

### OTP Generation & HMAC-SHA256 Hashing
A 6-digit code has only 900,000 possibilities (100000–999999).
* **Generation:** Generated using Python's `secrets` module, which draws from the operating system's cryptographic random number generator:
  ```python
  otp_code = f"{secrets.randbelow(900000) + 100000}"
  ```
* **Why Plain Hashes Are Unsafe:** A simple SHA-256 hash of a 6-digit number can be reversed via precomputed rainbow tables in seconds.
* **The HMAC Solution:** Swan Drive uses HMAC-SHA256, hashing the OTP using a server-side secret key:
  ```python
  otp_hash = hmac.new(SECRET_KEY.encode(), otp_code.encode(), hashlib.sha256).hexdigest()
  ```
  An attacker inspecting Redis cannot determine the original OTP without the server's private secret.

### Argon2id Password Hashing
Passwords are never stored in plaintext—even temporarily in Redis:
* When registration begins, the password is immediately hashed with **Argon2id**.
* Argon2id is a memory-hard algorithm designed to resist GPU-based cracking attacks.
* The raw password is discarded from memory immediately after hashing.

### Resend Email Delivery
* Verification emails are sent via Resend's REST API using HTTPS requests.
* **Synchronous Error Handling:** The backend waits for Resend's confirmation before staging data in Redis. If Resend reports an error (e.g., unverified domain or invalid recipient), the API returns `502 Bad Gateway` and refuses to create a pending session.

### MySQL Permanent Storage
* MySQL remains completely protected from unverified user submissions.
* Only after the user enters the correct OTP does the backend execute:
  ```sql
  INSERT INTO users (email, hashed_password, status, created_at)
  VALUES ('user@example.com', '$argon2id$...', 'active', UTC_TIMESTAMP());
  ```

### JWT Authentication
* Following successful verification, the backend creates a signed JSON Web Token (JWT) containing the user ID as subject (`sub`).
* Protected endpoints decode this token, verify its HS256 signature, and enforce user data isolation.

---

## 5. Abuse Prevention & Edge Cases

1. **Brute-Force Protection:**
   The attempt counter increments on every mismatch. On the **5th incorrect attempt**, the key is deleted immediately. A 6th attempt is impossible because the key no longer exists.
2. **Race Condition & Concurrency Defense:**
   If two verification requests arrive at the exact same millisecond, an atomic Redis Lua script ensures only the **first** request matches and deletes the key. The second request immediately receives `NOT_FOUND` and fails.
3. **Login Rate Limiting:**
   Failed login attempts increment a distributed counter in Redis. After 5 incorrect password attempts within 15 minutes, the account is temporarily locked with `429 Too Many Requests`.

---

## 6. Security Responsibilities Summary

| Component | Primary Security Role |
| :--- | :--- |
| **FastAPI** | Input validation, coordinating Redis/MySQL, enforcing rate limits. |
| **Upstash Redis** | Ephemeral storage (10m TTL), attempt limiting (5 max), cooldowns (60s). |
| **Argon2id** | Cryptographic protection of passwords while pending in Redis and permanently in MySQL. |
| **HMAC-SHA256** | Keyed protection of 6-digit OTPs against rainbow-table attacks. |
| **Resend API** | Reliable delivery of verification emails with failure detection. |
| **AWS RDS MySQL** | Clean source of truth for verified accounts; completely shielded from fake accounts. |
| **JWT** | Stateless 30-minute bearer tokens enforcing tenant isolation across all private files. |
