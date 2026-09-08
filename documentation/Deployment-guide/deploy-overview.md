# Deployment Overview: Personal Knowledge Base on AWS EC2

> **Role:** Senior DevOps Architect / Tech Lead  
> **Audience:** Freshers / developers deploying this project to AWS for the first time  
> **Strategy:** Use two progressive phases. First make the application work on one EC2 server. Only after that add automation, a domain, HTTPS, monitoring, and rollback.

---

## 1. Purpose of this Document

This document is the **map of the complete deployment journey** for the Personal Knowledge Base application.

It explains:

- **What** we are deploying.
- **Why** each component is needed.
- **How** the components communicate.
- **What** must be completed in Phase 1 and Phase 2.
- **Which detailed document** contains the actual commands.

The goal is that a fresher can understand the architecture before running commands.

| Document | Purpose |
| :--- | :--- |
| **`deploy-overview.md`** | High-level roadmap, architecture diagrams, decisions, security rules, and glossary |
| **`deploy-1.md`** | Step-by-step commands for **Phase 1 — MVP Core Deployment** |
| **`deploy-2.md`** | Step-by-step commands for **Phase 2 — Production Automation & Advanced Setup** |

> **Important:** Do not try to learn or configure everything at once. Finish Phase 1 first. Once the application works reliably, move to Phase 2.

---

## 2. Target Architecture

The application will run on **one Ubuntu EC2 instance**.

Inside the EC2 server, Docker Compose runs four containers:

- `mysql` — stores users and application metadata.
- `redis` — stores RAG/cache data.
- `qdrant` — stores vector embeddings for semantic search.
- `backend` — FastAPI application running with Gunicorn + Uvicorn workers.

Nginx runs directly on the Ubuntu host rather than inside Docker.

Nginx has two main jobs:

1. Serve the built React frontend.
2. Receive API requests and forward them to the FastAPI backend.

The backend communicates with external services:

- **Backblaze B2** — object/file storage.
- **Google Gemini** — embeddings and text generation.

### 2.1 Simple Architecture Diagram

The easiest way to understand the deployment is:

```text
                         INTERNET
                            │
                            │ HTTP :80
                            ▼
                  ┌───────────────────┐
                  │      NGINX        │
                  │                   │
                  │  1. React files   │
                  │  2. API proxy     │
                  └─────────┬─────────┘
                            │
                            │ /auth
                            │ /files
                            │ /search
                            │ /system
                            │ /documents
                            │ /rag
                            ▼
                  ┌───────────────────┐
                  │  FASTAPI BACKEND  │
                  │ Gunicorn + Uvicorn│
                  │    :8000          │
                  └───────┬───────────┘
                          │
              ┌───────────┼────────────┐
              │           │            │
              ▼           ▼            ▼
        ┌──────────┐ ┌─────────┐ ┌──────────┐
        │  MySQL   │ │  Redis  │ │  Qdrant  │
        │  :3306   │ │  :6379  │ │  :6333   │
        └──────────┘ └─────────┘ └──────────┘
              │           │            │
              └───────────┴────────────┘
                    INTERNAL ONLY
```

### External Services

The backend also communicates with cloud services over HTTPS:

```text
                         ┌─────────────────────┐
                         │    FastAPI Backend  │
                         └──────────┬──────────┘
                                    │
                         HTTPS / Internet
                          ┌─────────┴─────────┐
                          ▼                   ▼
                 ┌────────────────┐   ┌────────────────┐
                 │  Backblaze B2  │   │ Google Gemini  │
                 │ File storage   │   │ AI / Embedding │
                 └────────────────┘   └────────────────┘
```

### 2.2 Request Flow

A normal browser request works like this:

```text
Browser
   │
   │ http://<elastic-ip>
   ▼
Nginx :80
   │
   ├── Request for "/" or frontend asset
   │       │
   │       └──► Serve React static files
   │
   └── Request for "/search", "/auth", etc.
           │
           └──► FastAPI :8000
                    │
                    ├──► MySQL
                    ├──► Redis
                    ├──► Qdrant
                    ├──► Backblaze B2
                    └──► Google Gemini
```

### 2.3 File Upload Flow

The application uses Backblaze B2 for file storage.

The important idea is that **large file data does not need to pass through FastAPI**.

```text
Browser
   │
   │ 1. Ask backend for upload permission
   ▼
FastAPI
   │
   │ 2. Generate presigned URL
   ▼
Browser
   │
   │ 3. Upload file directly
   ▼
Backblaze B2
```

For downloads, the same idea can be used:

```text
Browser ──► FastAPI ──► presigned URL
   │
   └──────────────────────► Backblaze B2
```

This reduces unnecessary load on the EC2 server.

### 2.4 Important Security Boundary

Only Nginx and SSH should be reachable from the public internet.

```text
PUBLIC
  │
  ├── :22  SSH       → your IP only
  ├── :80  HTTP      → Nginx
  └── :443 HTTPS     → Nginx (Phase 2)

PRIVATE
  ├── :8000 FastAPI
  ├── :3306 MySQL
  ├── :6379 Redis
  └── :6333 Qdrant
```

MySQL, Redis, Qdrant, and FastAPI should **not** be directly exposed to the internet.

---

## 3. Two-Phase Strategy At a Glance

| # | Phase | Focus | Goal | Detail Doc |
| :-- | :--- | :--- | :--- | :--- |
| **1** | **MVP Core Deployment** | EC2 + Docker + backend + frontend + Nginx | Get the complete application working on an EC2 IP | `deploy-1.md` |
| **2** | **Production Automation & Advanced Setup** | CI/CD + domain + HTTPS + monitoring + rollback | Make deployment safer and mostly automatic | `deploy-2.md` |

### Phase 1

```text
Your computer
     │
     │ git push
     ▼
  GitHub
     │
     │ manual git clone/pull
     ▼
  AWS EC2
     │
     ├── Nginx
     └── Docker Compose
           ├── FastAPI
           ├── MySQL
           ├── Redis
           └── Qdrant
```

### Phase 2

```text
Your computer
     │
     │ git push
     ▼
  GitHub
     │
     │ GitHub Actions
     ▼
 Test → Build → Deploy
     │
     ▼
  AWS EC2
```

> **Rule #1:** Do not start Phase 2 until Phase 1 works correctly.

---

# 4. Phase 1 — MVP Core Deployment

**Goal:** Get the entire application running on one EC2 server with a manual deployment process.

At the end of Phase 1, you should be able to open:

```text
http://<elastic-ip>
```

and use the application.

For example:

```text
Browser
   │
   ▼
http://<elastic-ip>
   │
   ▼
Nginx
   │
   ├── React frontend
   │
   └── FastAPI backend
          │
          ├── MySQL
          ├── Redis
          ├── Qdrant
          ├── Backblaze B2
          └── Gemini
```

## 4.1 Step Checklist

| Step | Task | What it produces | Where to get commands |
| :-- | :--- | :--- | :--- |
| **1** | **Prepare the project** | Clean Git repository, production configuration plan | `deploy-1.md` §1 |
| **2** | **EC2 Provisioning & Base Server Setup** | Ubuntu EC2, Elastic IP, Security Group, swap | `deploy-1.md` §2 |
| **3** | **Connect to EC2** | SSH access from your computer | `deploy-1.md` §3 |
| **4** | **Install Docker & Compose** | Docker Engine + Compose plugin | `deploy-1.md` §4 |
| **5** | **Clone the project** | Project source code on EC2 | `deploy-1.md` §5 |
| **6** | **Create production `.env`** | Production database, B2, Gemini, Redis, Qdrant configuration | `deploy-1.md` §6 |
| **7** | **Containerize services** | `docker-compose.yml` + backend `Dockerfile` + persistent volumes | `deploy-1.md` §7 |
| **8** | **Run backend** | FastAPI with Gunicorn + Uvicorn | `deploy-1.md` §8 |
| **9** | **Build frontend** | Optimised React/Vite static files | `deploy-1.md` §9 |
| **10** | **Install & configure Nginx** | React static hosting + API reverse proxy | `deploy-1.md` §10 |
| **11** | **Configure firewall** | Only required ports are reachable | `deploy-1.md` §11 |
| **12** | **Run database migrations** | Database schema updated with Alembic | `deploy-1.md` §12 |
| **13** | **Smoke test** | Confirm login, upload, search, and health check work | `deploy-1.md` §13 |
| **14** | **Document recovery steps** | Basic restart, logs, and backup commands | `deploy-1.md` §14 |

---

## 4.2 Step 1 — Prepare the Project

Before touching AWS, make sure the local project is in a deployable state.

Check:

```text
Backend
├── FastAPI
├── requirements.txt / pyproject.toml
├── main.py
└── app/

Frontend
├── Vite
├── package.json
├── package-lock.json
└── src/

Others
└── .env
```

### Important checks

- Commit your current working changes.
- Push the latest code to GitHub.
- Make sure `.env` is ignored by Git.
- Keep `.env.example` in Git with placeholder values.
- Commit `frontend/package-lock.json` so `npm ci` is reproducible.
- Add `gunicorn` to the backend dependencies.

> **Important:** CI/CD and deployment work with committed code. If your changes are only on your computer and not committed, the server cannot get those changes through Git.

---

## 4.3 Step 2 — EC2 Provisioning

Create an EC2 instance using Ubuntu 24.04 LTS or Ubuntu 22.04 LTS.

The planned small/free-tier instance is approximately:

```text
2 vCPU
2 GB RAM
```

### Security Group

At launch, configure inbound access approximately like this:

| Port | Protocol | Source | Purpose |
| :--- | :--- | :--- | :--- |
| `22` | TCP | **Your IP only** | SSH |
| `80` | TCP | `0.0.0.0/0` | HTTP / Nginx |
| `443` | TCP | `0.0.0.0/0` | HTTPS in Phase 2 |

Do **not** create public inbound rules for:

```text
3306  MySQL
6379  Redis
6333  Qdrant
8000  FastAPI
```

### Elastic IP

Allocate and associate an Elastic IP with the EC2 instance.

Why?

```text
Normal public IP
EC2 restart
     ↓
IP may change

Elastic IP
EC2 restart
     ↓
Same public IP
```

This makes Phase 1 easier because your frontend and Nginx configuration can consistently use the same IP.

---

## 4.4 Step 3 — Connect to EC2

From Windows, you can use:

- PowerShell / Windows Terminal with OpenSSH.
- WSL.
- Another SSH client.

Typical connection:

```bash
ssh -i "your-key.pem" ubuntu@<elastic-ip>
```

Once connected:

```text
Your computer
     │
     │ SSH
     ▼
Ubuntu EC2
```

From this point, most deployment commands are executed **inside EC2**.

---

## 4.5 Step 4 — Basic Server Preparation

Update Ubuntu:

```bash
sudo apt update
sudo apt upgrade -y
```

### Add Swap

A 2 GB server has limited RAM, while this project runs:

```text
Ubuntu
Docker
Nginx
FastAPI
MySQL
Redis
Qdrant
```

A swap file gives the system additional emergency memory using disk space.

Conceptually:

```text
RAM
2 GB
 │
 │ memory pressure
 ▼
Swap
2 GB disk
```

Swap is much slower than RAM, but it can reduce the chance of the server being killed when memory usage temporarily becomes too high.

> **Recommendation:** Configure the planned 2 GB swap before starting the full Docker stack.

---

## 4.6 Step 5 — Install Docker & Docker Compose

Docker will run the application services as containers.

Think of containers as isolated environments:

```text
Docker
│
├── FastAPI container
├── MySQL container
├── Redis container
└── Qdrant container
```

Docker Compose lets us manage all of them from one file:

```text
docker-compose.yml
```

Then one command can start the stack:

```bash
docker compose up -d
```

---

## 4.7 Step 6 — Clone the Project

On EC2:

```bash
git clone <your-repository>
cd Personal_Knowledge_Base
```

The server should now contain:

```text
Personal_Knowledge_Base/
├── backend/
├── frontend/
├── others/
├── docker-compose.yml
└── ...
```

Do not commit the production `.env` to GitHub.

---

## 4.8 Step 7 — Production Environment Variables

The local development configuration uses `localhost`.

That works when everything runs directly on your computer:

```text
FastAPI
   │
   └── localhost:3306
          │
          ▼
        MySQL
```

Inside Docker, `localhost` means **the current container**, not another container.

Therefore Compose service names are used:

```text
FastAPI container
   │
   ├── mysql:3306
   ├── redis:6379
   └── qdrant:6333
```

### Production configuration example

The production `.env` should contain values similar to:

```dotenv
# Core
SECRET_KEY=<generate-a-new-random-production-value>
VITE_API_URL=/

# Database
DATABASE_URL=mysql+pymysql://pkb:<db-password>@mysql:3306/personal_knowledge_base

# Backblaze B2
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=eu-central-003
AWS_ENDPOINT_URL=https://s3.eu-central-003.backblazeb2.com
S3_BUCKET_NAME=personal-knowledge-base

# Gemini
GEMINI_API_KEY=...

# Redis
REDIS_URL=redis://redis:6379/0

# Qdrant
QDRANT_HOST=http://qdrant:6333

# CORS
CORS_ORIGINS=["http://<elastic-ip>"]
```

### Secrets

The following are secrets:

```text
SECRET_KEY
DB password
AWS/B2 secret key
Gemini API key
```

Generate fresh production values where appropriate.

Never commit them to GitHub.

---

## 4.9 Why `VITE_API_URL=/` Is Used

The frontend currently uses an Axios base URL.

Instead of:

```text
http://localhost:8000
```

use:

```text
/
```

This is a **relative URL**.

For example:

```text
Browser
   │
   │ /search
   ▼
Nginx
   │
   ▼
FastAPI
```

This means the frontend uses the same host that served the frontend.

So:

```text
http://<elastic-ip>
```

works.

Later:

```text
https://example.com
```

can also work without hardcoding the domain into the frontend API URL.

---

## 4.10 Step 8 — Docker Compose

The Compose file should define:

```text
docker-compose.yml
│
├── mysql
├── redis
├── qdrant
└── backend
```

### Persistent volumes

Database/vector data should be stored in named Docker volumes:

```text
mysql_data
    ↓
MySQL database files

redis_data
    ↓
Redis persistent data

qdrant_data
    ↓
Qdrant vector data
```

The important reason is:

```text
Container rebuilt/deleted
          ↓
Container data may disappear

Named volume
          ↓
Persistent data survives
```

### Internal networking

Docker Compose creates a private network for the services.

```text
Docker Network
│
├── backend
├── mysql
├── redis
└── qdrant
```

The backend can use:

```text
mysql
redis
qdrant
```

as hostnames.

These services do not need public ports.

### Start the stack

After configuration:

```bash
docker compose up -d
```

Check:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs
```

Backend logs only:

```bash
docker compose logs backend
```

---

## 4.11 Step 9 — Backend: Gunicorn + Uvicorn

FastAPI is an ASGI application.

Uvicorn is commonly used to run it.

For production, the plan uses:

```text
Gunicorn
   │
   ├── Uvicorn worker 1
   └── Uvicorn worker 2
             │
             ▼
          FastAPI
```

Example command:

```bash
gunicorn \
  -k uvicorn.workers.UvicornWorker \
  -w 2 \
  -b 0.0.0.0:8000 \
  main:app
```

The two workers are intentionally small because the EC2 server has limited memory.

> Do not blindly increase the worker count on a 2 GB server. More workers mean more memory usage.

---

## 4.12 Step 10 — Frontend Build

Vite creates a production version of the React application.

Typical commands:

```bash
cd frontend
npm ci
npm run build
```

The result is normally:

```text
frontend/
└── dist/
    ├── index.html
    ├── assets/
    └── ...
```

Nginx will serve this `dist` directory.

Conceptually:

```text
React source
     │
     │ npm run build
     ▼
frontend/dist/
     │
     ▼
Nginx
     │
     ▼
Browser
```

Node.js is needed to build the frontend, but Nginx does **not** need to run Node.js to serve the finished static files.

---

## 4.13 Step 11 — Nginx

Nginx is the **front door** of the application.

It receives browser requests and decides where they should go.

```text
Browser
   │
   ▼
Nginx :80
   │
   ├── "/" and frontend assets
   │       └──► /var/www/pkb
   │
   └── "/auth", "/files", "/search", ...
           └──► FastAPI :8000
```

### SPA fallback

React is a Single Page Application.

If the user visits a route directly, Nginx should fall back to:

```text
index.html
```

Conceptually:

```text
Unknown frontend route
        │
        ▼
   index.html
        │
        ▼
     React Router
```

### API routes

The following routes are sent to FastAPI:

```text
/auth
/files
/search
/system
/documents
/rag
```

Nginx proxies these requests to the backend.

---

## 4.14 Step 12 — Firewall

There are two layers of protection:

```text
Internet
   │
   ▼
AWS Security Group
   │
   ▼
Ubuntu UFW
   │
   ▼
Nginx / SSH
```

Recommended public access:

```text
22  → SSH, your IP only
80  → HTTP
443 → HTTPS, Phase 2
```

Internal application services:

```text
8000 → private
3306 → private
6379 → private
6333 → private
```

> **Critical:** Never publish MySQL, Redis, Qdrant, or the FastAPI port directly to the internet unless there is a specific, carefully secured reason.

---

## 4.15 Step 13 — Database Migrations

The application uses Alembic for database schema migrations.

Think of Alembic as:

> **Git for database structure.**

For example:

```text
Migration 1
   ↓
Create users table

Migration 2
   ↓
Add files table

Migration 3
   ↓
Add search-related column
```

Run:

```bash
docker compose exec backend alembic upgrade head
```

This brings the production database to the latest schema.

---

## 4.16 Step 14 — Smoke Test

A smoke test is a quick test to answer:

> "Is the deployment basically working?"

Start with:

```text
http://<elastic-ip>
```

Then test:

- Frontend loads.
- Registration works.
- Login works.
- `/system/ping` works.
- File upload works.
- File processing/indexing works.
- Search works.
- RAG response works.
- B2 upload/download works.

Health check:

```text
http://<elastic-ip>/system/ping
```

Expected result should indicate that the backend is alive.

---

## 4.17 Basic Troubleshooting Commands

If something does not work, do not immediately rebuild everything.

First check:

### Container status

```bash
docker compose ps
```

### Backend logs

```bash
docker compose logs backend
```

### All service logs

```bash
docker compose logs
```

### Follow live logs

```bash
docker compose logs -f backend
```

### Restart services

```bash
docker compose restart
```

### Rebuild backend

```bash
docker compose up -d --build backend
```

### Check Nginx configuration

```bash
sudo nginx -t
```

### Check Nginx status

```bash
sudo systemctl status nginx
```

---

# 5. Phase 1 Important Decisions

## 5.1 Instance

Planned small EC2 instance:

```text
2 vCPU
~2 GB RAM
```

Because this is a small machine:

- Keep the number of Gunicorn workers low.
- Configure swap.
- Keep MySQL memory usage controlled.
- Monitor disk and memory.
- Avoid running unnecessary services.

> **Note:** AWS free-tier eligibility and instance availability can change. Verify the current AWS pricing/free-tier rules when creating the instance.

---

## 5.2 HTTP Only in Phase 1

Phase 1 uses:

```text
http://<elastic-ip>
```

There is no custom domain yet.

HTTPS is postponed to Phase 2.

### Important security warning

HTTP does **not** encrypt traffic.

Therefore:

```text
Browser ── HTTP ──► EC2
```

is not appropriate for sensitive production data.

For a personal/educational MVP, this can be treated as a temporary deployment step.

When the application becomes a real public service, use:

```text
Browser
   │
   │ HTTPS :443
   ▼
Nginx
```

---

## 5.3 Backblaze B2

Backblaze B2 remains the application's object storage.

The architecture is:

```text
Application
     │
     ▼
Backblaze B2
```

The application already uses an S3-compatible API.

Therefore, moving to AWS S3 later should mainly involve changing configuration rather than rewriting the complete file-storage architecture.

---

## 5.4 Secrets

Production secrets should exist only on the server.

Example:

```text
EC2
└── others/.env
```

Do not put real secrets in:

```text
GitHub
Git repository
Dockerfile
frontend source code
README
```

The production `.env` is already intended to remain outside Git.

---

# 6. Phase 2 — Production Automation & Advanced Setup

**Goal:** After Phase 1 is stable, make deployment easier, safer, and more professional.

Phase 2 adds:

1. CI/CD.
2. Custom domain.
3. HTTPS.
4. Monitoring and logging.
5. Better secret management.
6. Rollbacks.
7. Automated operational tasks.

---

## 6.1 Phase 2 Step Checklist

| # | Task | What it produces | Detail Doc |
| :-- | :--- | :--- | :--- |
| **1** | **GitHub Actions CI/CD** | Automatic test/build/deploy pipeline | `deploy-2.md` §1 |
| **2** | **Custom Domain + HTTPS** | Domain + trusted SSL certificate | `deploy-2.md` §2 |
| **3** | **Monitoring & Logging** | Health checks, logs, disk/memory visibility | `deploy-2.md` §3 |
| **4** | **Secret Management** | Safer handling of deployment credentials | `deploy-2.md` §4 |
| **5** | **Backups** | Recovery plan for MySQL/Qdrant data | `deploy-2.md` §5 |
| **6** | **Rollback Strategy** | Ability to return to a known-good release | `deploy-2.md` §6 |

---

# 7. CI/CD — Simple Explanation

CI/CD sounds complicated, but the basic idea is simple:

> **Push code to GitHub → automatically test it → build it → deploy it to EC2.**

### Without CI/CD

```text
Developer
   │
   │ git push
   ▼
GitHub

Then manually:

SSH → EC2
     ↓
git pull
     ↓
build
     ↓
restart
```

### With CI/CD

```text
Developer
   │
   │ git push
   ▼
GitHub
   │
   ▼
GitHub Actions
   │
   ├── Run tests
   ├── Build frontend
   ├── Build backend
   ├── Deploy to EC2
   ├── Run migrations
   └── Health check
```

GitHub Actions is basically an **automation robot** that performs the deployment steps for you.

---

## 7.1 CI/CD Pipeline

```text
                 git push
                    │
                    ▼
             ┌──────────────┐
             │    GitHub    │
             └──────┬───────┘
                    │
                    ▼
          ┌─────────────────────┐
          │   GitHub Actions    │
          └──────────┬──────────┘
                     │
             ┌───────┴────────┐
             ▼                ▼
       Backend tests     Frontend build
             │                │
             └───────┬────────┘
                     ▼
              Deploy via SSH
                     │
                     ▼
                  EC2
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
      Docker Compose          Nginx
          │
          ├── FastAPI
          ├── MySQL
          ├── Redis
          └── Qdrant
                     │
                     ▼
              Health check
              /system/ping
```

### Release rule

Only code that is committed and pushed to GitHub should be deployed.

```text
Local uncommitted code
        │
        └──► NOT deployed

Committed + pushed code
        │
        └──► Can be deployed
```

---

# 8. Custom Domain + HTTPS

Phase 2 replaces:

```text
http://<elastic-ip>
```

with something like:

```text
https://example.com
```

The basic flow is:

```text
Domain
   │
   │ DNS A record
   ▼
Elastic IP
   │
   ▼
Nginx :443
   │
   ▼
FastAPI :8000
```

HTTPS is provided using a trusted certificate.

The planned tools are:

```text
Let's Encrypt
      +
Certbot
      +
Nginx
```

The certificate should also be configured for automatic renewal.

---

# 9. Phase 2 Architecture

```text
                         USER
                           │
                           │ HTTPS
                           ▼
                  ┌─────────────────┐
                  │      DOMAIN     │
                  │  example.com    │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │      NGINX      │
                  │      :443       │
                  │ SSL termination  │
                  │ static + proxy   │
                  └────────┬────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │   Docker Compose     │
                │                      │
                │  ┌────────────────┐  │
                │  │    Backend     │  │
                │  │ FastAPI        │  │
                │  └───────┬────────┘  │
                │          │           │
                │    ┌─────┼─────┐     │
                │    ▼     ▼     ▼     │
                │ MySQL  Redis Qdrant  │
                └──────────────────────┘

GitHub
   │
   │ push to main
   ▼
GitHub Actions
   │
   ├── Test
   ├── Build
   └── Deploy
          │
          ▼
         EC2
```

---

# 10. Monitoring & Operations

Once the application is public, you need to know when something goes wrong.

Start simple.

### Health check

```text
/system/ping
```

### Docker status

```bash
docker compose ps
```

### Docker logs

```bash
docker compose logs
```

### Nginx logs

```text
/var/log/nginx/
```

### Things to watch

```text
CPU
RAM
Swap
Disk
Container status
Database availability
Application health
```

For this small EC2 server, memory and disk usage are particularly important.

---

# 11. Backups

Docker volumes protect data from container rebuilds, but **volumes are not the same thing as backups**.

For example:

```text
Docker volume
     │
     └── protects against accidental container deletion

Backup
     │
     └── protects against server/disk failure
```

At minimum, create a backup plan for:

```text
MySQL
Qdrant
Important application configuration
```

MySQL can be backed up using a database dump such as:

```bash
mysqldump
```

Qdrant backup/snapshot procedures should also be documented.

> A production system should have a recovery procedure, not just a backup file.

---

# 12. Security & Port Reference

| Port | Purpose | Reachable from Internet? | Rule |
| :--- | :--- | :--- | :--- |
| `22` | SSH administration | **Yes, but your IP only** | Restrict to your IP |
| `80` | HTTP / Nginx | Yes | Public |
| `443` | HTTPS / Nginx | Yes | Public, Phase 2 |
| `8000` | FastAPI | **No** | Host-only/internal |
| `3306` | MySQL | **No** | Docker network only |
| `6333` | Qdrant | **No** | Docker network only |
| `6379` | Redis | **No** | Docker network only |

### Security rule to remember

```text
Internet
   │
   ├── SSH :22 ───────────────► EC2
   │                            (your IP only)
   │
   └── HTTP/HTTPS :80/:443 ──► Nginx
                                │
                                ▼
                              Backend
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
                  MySQL       Redis       Qdrant
                 PRIVATE     PRIVATE     PRIVATE
```

> If you see `0.0.0.0:3306`, `0.0.0.0:6379`, or `0.0.0.0:6333` exposed publicly, stop and fix the configuration.

---

# 13. Important Deployment Concepts for Freshers

## 13.1 EC2

**EC2 = a virtual Linux computer in AWS.**

Instead of running the application on your laptop:

```text
Your laptop
   └── Application
```

you run it on:

```text
AWS
└── EC2
    └── Application
```

---

## 13.2 Docker

**Docker packages applications into containers.**

For this project:

```text
Docker
├── Backend container
├── MySQL container
├── Redis container
└── Qdrant container
```

Each service is isolated but can communicate through the Docker network.

---

## 13.3 Docker Compose

**Docker Compose manages multiple containers together.**

Instead of:

```bash
docker run mysql
docker run redis
docker run qdrant
docker run backend
```

you can use:

```bash
docker compose up -d
```

because `docker-compose.yml` describes the whole stack.

---

## 13.4 Nginx

**Nginx is the front door of the website.**

It receives requests and decides:

```text
Frontend request
     ↓
Serve React files

API request
     ↓
Forward to FastAPI
```

---

## 13.5 Reverse Proxy

A reverse proxy is simply a server that receives a request and forwards it to another service.

```text
Browser
   ↓
Nginx
   ↓
FastAPI
```

Nginx is acting as the reverse proxy.

---

## 13.6 Gunicorn

Gunicorn is used to run the FastAPI application with multiple worker processes.

```text
Gunicorn
├── Worker 1
└── Worker 2
      ↓
   FastAPI
```

It is used instead of relying only on the simple development server.

---

## 13.7 Docker Volume

A volume is persistent storage for containers.

```text
MySQL container
       │
       ▼
mysql_data volume
       │
       ▼
Database data
```

Rebuilding the container does not automatically delete the volume.

---

## 13.8 Security Group

AWS Security Group is an AWS-level firewall.

It controls which network traffic can reach the EC2 instance.

---

## 13.9 UFW

UFW is Ubuntu's firewall.

So you can have:

```text
AWS Security Group
        ↓
Ubuntu UFW
        ↓
Application
```

Both should be configured consistently.

---

## 13.10 Elastic IP

An Elastic IP is a stable public IP associated with the EC2 instance.

It prevents the public address from changing when the instance is restarted, subject to AWS's current pricing/usage rules.

---

## 13.11 Swap

Swap is disk space that Linux can use when RAM is under pressure.

```text
RAM
 ↓
Full / under pressure
 ↓
Swap on disk
```

It is slower than RAM, so it is a safety net rather than a replacement for RAM.

---

## 13.12 Alembic

Alembic manages database schema changes.

Think:

```text
Git
 ↓
Tracks code changes

Alembic
 ↓
Tracks database structure changes
```

---

## 13.13 Presigned URL

A presigned URL is a temporary URL that allows a client to upload/download an object directly from object storage.

For example:

```text
Browser
   │
   │ request upload URL
   ▼
Backend
   │
   │ temporary URL
   ▼
Browser
   │
   │ direct upload
   ▼
Backblaze B2
```

---

## 13.14 CI/CD

CI/CD is automated software delivery.

In this project:

```text
git push
   ↓
GitHub Actions
   ↓
test
   ↓
build
   ↓
deploy
   ↓
health check
```

You do not need CI/CD to complete the first deployment.

---

# 14. Decision Log

| Topic | Decision | Reason |
| :--- | :--- | :--- |
| **Hosting** | Single EC2 | Simple and low-cost for the MVP |
| **Operating System** | Ubuntu | Familiar Linux environment and strong Docker support |
| **Database** | MySQL in Docker | Simple one-server architecture |
| **Cache** | Redis in Docker | Keeps the MVP architecture simple |
| **Vector DB** | Qdrant in Docker | Required for semantic/vector search |
| **Object storage** | Backblaze B2 | Already integrated with the application |
| **Backend** | FastAPI + Gunicorn/Uvicorn | Production-oriented ASGI setup |
| **Frontend** | Vite React static build | Nginx can serve static files directly |
| **Reverse proxy** | Nginx on host | Simple static hosting and API proxy |
| **SSL** | Phase 2 | Phase 1 uses an Elastic IP without a domain |
| **CI/CD** | Phase 2 | First understand and stabilize manual deployment |
| **Secrets** | Server-side `.env` | Prevent secrets from entering Git |
| **Persistence** | Docker named volumes | Preserve MySQL/Redis/Qdrant data across container rebuilds |
| **Firewall** | AWS Security Group + UFW | Defense at both AWS and OS levels |

---

# 15. Preparedness Checklist

Before starting Phase 1:

### AWS

- [ ] AWS account ready.
- [ ] EC2 instance type selected.
- [ ] Ubuntu 24.04/22.04 selected.
- [ ] SSH key pair (`.pem`) downloaded.
- [ ] Security Group configured.
- [ ] Elastic IP allocated and associated.

### GitHub / Project

- [ ] Latest code pushed to GitHub.
- [ ] Current local changes committed.
- [ ] `.env` is not tracked by Git.
- [ ] `.env.example` exists.
- [ ] `frontend/package-lock.json` is committed.
- [ ] `gunicorn` is included in backend dependencies.
- [ ] Dockerfile is prepared.
- [ ] `docker-compose.yml` is prepared.

### External Services

- [ ] Backblaze B2 credentials available.
- [ ] Gemini API key available.
- [ ] Production database password prepared.
- [ ] New production `SECRET_KEY` generated.

### Before Going Public

- [ ] MySQL is not publicly exposed.
- [ ] Redis is not publicly exposed.
- [ ] Qdrant is not publicly exposed.
- [ ] FastAPI `:8000` is not publicly exposed.
- [ ] SSH is restricted to your IP.
- [ ] `/system/ping` works.
- [ ] Login works.
- [ ] File upload works.
- [ ] Search works.
- [ ] RAG works.

---

# 16. Deployment Order — The Big Picture

If you forget everything else, remember this order:

```text
1. Prepare code
      │
      ▼
2. Create EC2
      │
      ▼
3. Configure Security Group
      │
      ▼
4. Connect using SSH
      │
      ▼
5. Update Ubuntu + configure swap
      │
      ▼
6. Install Docker
      │
      ▼
7. Clone GitHub repository
      │
      ▼
8. Create production .env
      │
      ▼
9. Start MySQL + Redis + Qdrant + Backend
      │
      ▼
10. Run Alembic migrations
      │
      ▼
11. Build React frontend
      │
      ▼
12. Install/configure Nginx
      │
      ▼
13. Configure UFW
      │
      ▼
14. Open http://<elastic-ip>
      │
      ▼
15. Test login + upload + search + RAG
      │
      ▼
          PHASE 1 COMPLETE 🎉
      │
      ▼
16. Later: CI/CD
      │
      ▼
17. Later: Domain
      │
      ▼
18. Later: HTTPS
      │
      ▼
19. Later: Monitoring + backups + rollback
      │
      ▼
          PHASE 2 COMPLETE
```

---

# 17. Final Mental Model

You do not need to memorize every command.

Understand these relationships:

```text
EC2
│
│  "The cloud computer"
│
├── Nginx
│     │
│     ├── serves React
│     └── forwards API requests
│
└── Docker
      │
      └── Docker Compose
            │
            ├── FastAPI
            │      │
            │      ├── MySQL
            │      ├── Redis
            │      ├── Qdrant
            │      ├── Backblaze B2
            │      └── Gemini
            │
            ├── MySQL volume
            ├── Redis volume
            └── Qdrant volume
```

And the deployment progression is:

```text
                 START
                   │
                   ▼
        ┌─────────────────────┐
        │   Phase 1           │
        │   Make it work      │
        │                     │
        │ EC2 + Docker        │
        │ + Nginx + FastAPI   │
        │ + MySQL/Redis/      │
        │   Qdrant            │
        └──────────┬──────────┘
                   │
                   │ stable?
                   ▼
        ┌─────────────────────┐
        │   Phase 2           │
        │   Make it better    │
        │                     │
        │ CI/CD + Domain      │
        │ + HTTPS + Backups   │
        │ + Monitoring        │
        │ + Rollback          │
        └─────────────────────┘
```

> **The main idea:** Phase 1 is not about building a perfect enterprise DevOps platform. It is about getting your application reliably running on one EC2 server. Once that works, Phase 2 improves automation and production safety.
