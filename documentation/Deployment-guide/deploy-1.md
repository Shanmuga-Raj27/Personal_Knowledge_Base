# Phase 1 — MVP Core Deployment Guide

> **Project:** Personal Knowledge Base  
> **Target:** AWS EC2 + Ubuntu + Docker Compose + Nginx  
> **Developer machine:** Windows 10 + Docker Desktop + VS Code CMD terminal  
> **Goal:** Get the complete application running on one EC2 server using an Elastic IP.
>
> **Important:** This guide intentionally does **not** contain real passwords, API keys, access keys, or other secrets. Use placeholders and keep real production values only in the server-side `.env` file.

---

## 📋 Navigation

| # | Section |
| :---: | :--- |
| — | [1. Before You Start](#1-before-you-start) |
| 1 | [Step 1 — Prepare the Project Locally](#2-step-1--prepare-the-project-locally) |
| 2 | [Step 2 — Check Required Local Tools](#3-step-2--check-required-local-tools) |
| 3 | [Step 3 — Create / Verify AWS EC2](#4-step-3--create--verify-aws-ec2) |
| 4 | [Step 4 — Allocate an Elastic IP](#5-step-4--allocate-an-elastic-ip) |
| 5 | [Step 5 — Connect to EC2 Using SSH](#6-step-5--connect-to-ec2-using-ssh) |
| 6 | [Step 6 — Prepare Ubuntu](#7-step-6--prepare-ubuntu) |
| 7 | [Step 7 — Configure Swap](#8-step-7--configure-swap) |
| 8 | [Step 8 — Install Docker on EC2](#9-step-8--install-docker-on-ec2) |
| 9 | [Step 9 — Clone the Project on EC2](#10-step-9--clone-the-project-on-ec2) |
| 10 | [Step 10 — Create the Production Environment File](#11-step-10--create-the-production-environment-file) |
| 11 | [Step 11 — Add / Verify Gunicorn Dependency](#12-step-11--add--verify-gunicorn-dependency) |
| 12 | [Step 12 — Create the Backend Dockerfile](#13-step-12--create-the-backend-dockerfile) |
| 13 | [Step 13 — Create Docker Compose](#14-step-13--create-docker-compose) |
| 14 | [Step 14 — Commit Deployment Files](#15-step-14--commit-deployment-files) |
| 15 | [Step 15 — Pull the New Code on EC2](#16-step-15--pull-the-new-code-on-ec2) |
| 16 | [Step 16 — Build and Start Docker Services](#17-step-16--build-and-start-docker-services) |
| 17 | [Step 17 — Understand the First Docker Startup](#18-step-17--understand-the-first-docker-startup) |
| 18 | [Step 18 — Check Individual Services](#19-step-18--check-individual-services) |
| 19 | [Step 19 — Check Backend Directly](#20-step-19--check-backend-directly) |
| 20 | [Step 20 — Run Alembic Database Migrations](#21-step-20--run-alembic-database-migrations) |
| 21 | [Step 21 — Build the Frontend](#22-step-21--build-the-frontend) |
| 22 | [Step 22 — Install Nginx on EC2](#23-step-22--install-nginx-on-ec2) |
| 23 | [Step 23 — Create the Frontend Static Directory](#24-step-23--create-the-frontend-static-directory) |
| 24 | [Step 24 — Configure Nginx](#25-step-24--configure-nginx) |
| 25 | [Step 25 — Enable the Nginx Site](#26-step-25--enable-the-nginx-site) |
| 26 | [Step 26 — Configure Ubuntu Firewall (UFW)](#27-step-26--configure-ubuntu-firewall-ufw) |
| 27 | [Step 27 — First Full Application Test](#28-step-27--first-full-application-test) |
| 28 | [Step 28 — Application Smoke Test](#29-step-28--application-smoke-test) |
| 29 | [Step 29 — Basic Docker Commands You Should Know](#30-step-29--basic-docker-commands-you-should-know) |
| 30 | [Step 30 — Basic Nginx Commands](#31-step-30--basic-nginx-commands) |
| 31 | [Step 31 — Basic EC2 Resource Checks](#32-step-31--basic-ec2-resource-checks) |
| 32 | [Step 32 — What to Do When Something Fails](#33-step-32--what-to-do-when-something-fails) |
| 33 | [Step 33 — Updating the Application Later](#34-step-33--updating-the-application-later) |
| 34 | [Step 34 — Data Persistence and What `docker compose down` Means](#35-step-34--data-persistence-and-what-docker-compose-down-means) |
| 35 | [Step 35 — Backup Reminder](#36-step-35--backup-reminder) |
| 36 | [Step 36 — Phase 1 Completion Checklist](#37-step-36--phase-1-completion-checklist) |

---

## 1. Before You Start

This guide assumes:

```text
Your Windows 10 PC
│
├── VS Code
├── VS Code integrated CMD terminal
├── Git
├── Node.js / npm
└── Docker Desktop
```

The production server will be:

```text
AWS
└── EC2
    └── Ubuntu
        ├── Docker
        │   └── Docker Compose
        │       ├── FastAPI
        │       ├── MySQL
        │       ├── Redis
        │       └── Qdrant
        │
        └── Nginx
```

### Where commands are run

This is important because this guide uses **two different terminals**.

| Label | Where you run it | Typical prompt |
| :--- | :--- | :--- |
| **LOCAL CMD** | VS Code → Terminal → Command Prompt on Windows | `C:\Users\YourName\project>` |
| **EC2 SSH** | The SSH session connected to Ubuntu EC2 | `ubuntu@ip-xxx:~$` |

Unless a section says **EC2 SSH**, assume the command is run in your **VS Code CMD terminal on Windows**.

Commands beginning with `sudo`, `apt`, or `systemctl` are Linux commands and should be run **inside the EC2 SSH session**, not Windows CMD.

---

# 2. Step 1 — Prepare the Project Locally

**Run everything in this section in: `LOCAL CMD — VS Code terminal`.**

Before deploying, make sure your local project is in a clean enough state.

### 2.1 Check Git status

```cmd
git status
```

**What it does:** Shows changed, untracked, and staged files.

You should review any important changes before deployment.

### 2.2 Add and commit your current work

```cmd
git add .
git commit -m "Prepare project for deployment"
```

**What they do:**

- `git add .` → stages changed files.
- `git commit ...` → creates a Git commit containing those changes.

If Git says there is nothing to commit, that is fine.

### 2.3 Push to GitHub

```cmd
git push origin main
```

**What it does:** Uploads your committed code to the GitHub `main` branch.

Your deployment server will later download this committed code.

> **Important:** CI/CD is not part of Phase 1. We are using a simple manual `git pull` workflow first.

---

# 3. Step 2 — Check Required Local Tools

**Run these commands in: `LOCAL CMD — VS Code terminal`.**

### Git

```cmd
git --version
```

### Node.js

```cmd
node --version
```

### npm

```cmd
npm --version
```

### Docker

```cmd
docker --version
```

### Docker Compose

```cmd
docker compose version
```

You should have Docker Desktop running before using Docker commands.

### Docker Desktop

On Windows 10:

1. Open **Docker Desktop**.
2. Wait until Docker reports that it is running.
3. Open your VS Code terminal.
4. Run:

```cmd
docker info
```

**What it does:** Checks whether the Docker engine is reachable.

If Docker Desktop is not running, Docker commands may fail.

---

# 4. Step 3 — Create / Verify AWS EC2

**This section is mostly AWS Console work.**

Open the AWS Console and create an EC2 instance.

Recommended starting setup:

| Setting | Recommended value |
| :--- | :--- |
| OS | Ubuntu 24.04 LTS |
| Architecture | x86_64 |
| Instance size | Small/free-tier-eligible option available to your account |
| Storage | Enough for OS + Docker images + application data |
| Key pair | Create/download `.pem` key |
| Security Group | Allow only required ports |

> **Important:** AWS free-tier rules, instance names, and pricing can change. Check the current AWS pricing/free-tier information before launching.

---

## 4.1 Security Group

Create these inbound rules:

| Port | Protocol | Source | Purpose |
| :--- | :--- | :--- | :--- |
| `22` | TCP | **Your IP** | SSH |
| `80` | TCP | `0.0.0.0/0` | HTTP / Nginx |
| `443` | TCP | `0.0.0.0/0` | Reserved for Phase 2 HTTPS |

Do **not** add public rules for:

```text
3306  MySQL
6379  Redis
6333  Qdrant
8000  FastAPI
```

The desired network is:

```text
                         INTERNET
                            │
                 ┌──────────┴──────────┐
                 │                     │
              :22 SSH               :80 HTTP
           Your IP only               │
                 │                     ▼
                 │                  Nginx
                 │                     │
                 │                     ▼
                 │                 FastAPI
                 │                     │
                 │          ┌──────────┼──────────┐
                 │          ▼          ▼          ▼
                 │       MySQL      Redis      Qdrant
                 │
                 └────── EC2 SERVER ─────────────────
```

---

# 5. Step 4 — Allocate an Elastic IP

**This section is done in the AWS Console.**

An Elastic IP gives the EC2 server a stable public IPv4 address.

Without a stable address:

```text
EC2 restart
   ↓
Public IP may change
```

With an Elastic IP:

```text
EC2 restart
   ↓
Same Elastic IP
```

After allocating it, associate it with your EC2 instance.

You will use this value later as:

```text
<ELASTIC-IP>
```

Do not replace the placeholder in this documentation with your actual IP.

---

# 6. Step 5 — Connect to EC2 Using SSH

**Run this from: `LOCAL CMD — VS Code terminal`.**

The exact SSH command depends on where your `.pem` file is stored.

Example:

```cmd
ssh -i "C:\path\to\your-key.pem" ubuntu@<ELASTIC-IP>
```

**What it does:** Opens a secure terminal connection from Windows to Ubuntu on EC2.

After connecting, your terminal should look similar to:

```text
ubuntu@ip-10-0-1-123:~$
```

From this point, you are working **inside EC2**.

### How to know which terminal you are using

**Windows CMD:**

```text
C:\Users\YourName\project>
```

**EC2 SSH:**

```text
ubuntu@ip-10-0-1-123:~$
```

> Keep this distinction in mind throughout the guide.

---

# 7. Step 6 — Prepare Ubuntu

**Run everything in this section in: `EC2 SSH`.**

## 7.1 Update package information

```bash
sudo apt update
```

**What it does:** Refreshes Ubuntu's list of available packages.

## 7.2 Upgrade installed packages

```bash
sudo apt upgrade -y
```

**What it does:** Installs available updates.

`-y` automatically answers "yes" to the confirmation prompt.

---

# 8. Step 7 — Configure Swap

**Run everything in this section in: `EC2 SSH`.**

The planned EC2 server has limited RAM.

Your application may run:

```text
Ubuntu
Docker
Nginx
FastAPI
MySQL
Redis
Qdrant
```

So swap provides a safety buffer.

Conceptually:

```text
             EC2 Memory
                 │
             ┌───▼───┐
             │  RAM  │
             └───┬───┘
                 │
          Memory pressure
                 │
             ┌───▼────┐
             │  Swap  │
             │ on disk│
             └────────┘
```

Create a 2 GB swap file:

```bash
sudo fallocate -l 2G /swapfile
```

**What it does:** Creates a 2 GB file that will be used as swap.

Set safe permissions:

```bash
sudo chmod 600 /swapfile
```

**What it does:** Restricts access to the swap file.

Format it as swap:

```bash
sudo mkswap /swapfile
```

Enable it:

```bash
sudo swapon /swapfile
```

Verify:

```bash
free -h
```

You should see a `Swap` entry.

### Make swap survive reboot

Add the swap file to `/etc/fstab`:

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Verify:

```bash
swapon --show
```

> Swap is not a replacement for RAM. It is slower and should be treated as an emergency buffer.

---

# 9. Step 8 — Install Docker on EC2

**Run everything in this section in: `EC2 SSH`.**

Docker is required on the Linux server because the production application will run in containers.

The target architecture is:

```text
EC2
│
└── Docker
    │
    └── Docker Compose
        ├── backend
        ├── mysql
        ├── redis
        └── qdrant
```

Install Docker using Docker's official Ubuntu installation instructions appropriate for your Ubuntu version.

After installation, verify:

```bash
docker --version
```

Verify Compose:

```bash
docker compose version
```

Test Docker:

```bash
sudo docker run hello-world
```

**What it does:** Downloads a tiny test image and runs it to confirm Docker works.

If Docker works but requires `sudo`, configure your Ubuntu user to use Docker without `sudo` according to Docker's official post-install instructions.

After changing group membership, reconnect to SSH before testing again.

Then:

```bash
docker ps
```

**What it does:** Lists currently running containers.

---

# 10. Step 9 — Clone the Project on EC2

**Run everything in: `EC2 SSH`.**

Go to your home directory:

```bash
cd ~
```

Clone the repository:

```bash
git clone <YOUR-GITHUB-REPOSITORY>
```

**What it does:** Downloads your GitHub repository to the EC2 server.

Enter the project:

```bash
cd <YOUR-PROJECT-DIRECTORY>
```

Check the files:

```bash
ls
```

You should see directories similar to:

```text
backend/
frontend/
others/
```

and eventually:

```text
docker-compose.yml
```

---

# 11. Step 10 — Create the Production Environment File

**Run everything in this section in: `EC2 SSH`.**

The application needs environment variables for:

- Database connection.
- Redis.
- Qdrant.
- Backblaze B2.
- Gemini.
- CORS.
- Application configuration.

The production `.env` should exist **only on the EC2 server**.

Recommended location:

```text
project/
└── others/
    └── .env
```

Do not commit this file.

Check Git status:

```bash
git status
```

The real `.env` should remain ignored.

---

## 11.1 Important Docker Networking Difference

Local development may use:

```text
localhost:3306
localhost:6379
localhost:6333
```

Inside Docker, this is different.

For example:

```text
FastAPI container
       │
       │ localhost:3306
       ▼
   FastAPI itself ❌
```

Instead, Compose service names are used:

```text
FastAPI container
       │
       ├── mysql:3306
       ├── redis:6379
       └── qdrant:6333
```

So the production configuration should use the Compose service names.

Conceptually:

```text
DATABASE_URL
       │
       ▼
    mysql:3306

REDIS_URL
       │
       ▼
    redis:6379

QDRANT_HOST
       │
       ▼
    qdrant:6333
```

### Important

Do **not** write real credentials in this documentation.

Use your real values only when creating the server's `.env`.

---

# 12. Step 11 — Add / Verify Gunicorn Dependency

**This change should normally be made locally first.**

### Run in: `LOCAL CMD`

If your project uses `requirements.txt`, add:

```text
gunicorn
```

You can also install it with `uv` locally if your project uses `uv`:

```cmd
uv add gunicorn
```

or, for a requirements-based environment:

```cmd
uv pip install gunicorn
```

Then update the requirements file if that is how your project manages dependencies:

```cmd
uv pip freeze > requirements.txt
```

Review the generated file before committing.

Then:

```cmd
git add .
git commit -m "Add Gunicorn for production"
git push origin main
```

### Why Gunicorn?

The production backend will use:

```text
Gunicorn
   │
   ├── Uvicorn worker 1
   └── Uvicorn worker 2
           │
           ▼
        FastAPI
```

For a small 2 GB server, keep the worker count conservative.

---

# 13. Step 12 — Create the Backend Dockerfile

**Create/edit the file locally.**

### Run/edit in: `LOCAL CMD + VS Code editor`

Create:

```text
backend/Dockerfile
```

**File reference:** [`backend/Dockerfile`](../../backend/Dockerfile)

This file builds the production backend image. It contains these stages:

| Stage | What it does |
| :--- | :--- |
| `FROM python:3.12-slim` | Small Python base image |
| `apt-get install` | System libraries needed by `pymupdf` (PDF extraction) |
| `COPY requirements.txt` + `pip install` | Install Python dependencies |
| `COPY . .` | Copy backend application code into the image |
| `EXPOSE 8000` | Document that the container listens on port 8000 |
| `CMD [gunicorn ...]` | Start Gunicorn with Uvicorn workers on startup |

### `pywin32` filtering

The `requirements.txt` contains `pywin32==312` (Windows-only). The Dockerfile uses `grep -v pywin32` to skip this line during `pip install` on Linux.

### `.dockerignore` file

Create:

```text
backend/.dockerignore
```

**File reference:** [`backend/.dockerignore`](../../backend/.dockerignore)

This file keeps the production image lean by excluding files that are not needed at runtime:

| Excluded | Reason |
| :--- | :--- |
| `.venv/` | Virtual environment (Docker installs its own) |
| `tests/` | Not needed in production |
| `streamlit_app/` | Alternative UI, not part of backend image |
| `data/` | Evaluation data, not needed at runtime |
| `__pycache__/` | Python bytecode cache |
| `.pytest_cache/` | Test cache |
| `.git/` | Git history not needed in image |
| `.env` | Secrets must never be baked into the image |
| `*.log`, `*.tmp` | Temporary files |

### Production command explained

The Dockerfile's `CMD` runs:

```text
gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 main:app
```

Meaning:

| Part | Meaning |
| :--- | :--- |
| `gunicorn` | Production process manager |
| `-k uvicorn.workers.UvicornWorker` | Use Uvicorn workers for FastAPI/ASGI |
| `-w 2` | Start 2 workers (conservative for 2 GB server) |
| `-b 0.0.0.0:8000` | Listen on all interfaces inside the container |
| `main:app` | Load the `app` object from `main.py` |

---

# 14. Step 13 — Create Docker Compose

**Create/edit locally in VS Code.**

### Run/edit in: `LOCAL CMD + VS Code editor`

Create:

```text
docker-compose.yml
```

**File reference:** [`docker-compose.yml`](../../docker-compose.yml)

This file defines four services that run together as one application stack:

### Target architecture

```text
Docker Compose
│
├── backend
│     │
│     ├── → mysql:3306
│     ├── → redis:6379
│     └── → qdrant:6333
│
├── mysql
│     └── mysql_data volume
│
├── redis
│     └── redis_data volume
│
└── qdrant
      └── qdrant_data volume
```

### Services defined

| Service | Image | Purpose |
| :--- | :--- | :--- |
| `backend` | Built from `backend/Dockerfile` | FastAPI application |
| `mysql` | `mysql:8.0` | Relational database |
| `redis` | `redis:7-alpine` | Cache layer |
| `qdrant` | `qdrant/qdrant:latest` | Vector database |

### Health checks

Every dependency service (`mysql`, `redis`, `qdrant`) has a health check. The backend uses:

```text
depends_on:
  mysql:
    condition: service_healthy
```

This means Docker Compose will **not start the backend until all three dependencies report healthy**. Without this, the backend might try to connect before MySQL or Qdrant are ready.

### Environment variables

The compose file passes environment variables to the backend container using `${VAR}` syntax. Compose reads these values from:

```text
others/.env    ← on the EC2 server
```

This means **all docker compose commands must include `--env-file ./others/.env`** so Compose knows where to find the values.

### Important port rule

The backend is published only to the EC2 host:

```text
127.0.0.1:8000:8000
```

This means:

```text
Internet ✗ → 8000

Nginx → 127.0.0.1:8000 → backend
```

MySQL, Redis, and Qdrant have **no public port mappings** — they are only reachable inside the Docker network.

### Why volumes?

Use persistent named volumes:

```text
mysql_data
redis_data
qdrant_data
```

because:

```text
Container rebuilt
      ↓
Container can be replaced

Named volume
      ↓
Data remains
```

Remember:

> Docker volumes are persistence, not a complete backup strategy.

---

# 15. Step 14 — Commit Deployment Files

**Run in: `LOCAL CMD`.**

Check your changes:

```cmd
git status
```

Review:

```text
backend/Dockerfile
backend/.dockerignore
docker-compose.yml
requirements.txt
others/.env.example
```

Do not commit:

```text
others/.env
```

Then:

```cmd
git add backend/Dockerfile backend/.dockerignore docker-compose.yml requirements.txt
git commit -m "Add Docker production deployment"
git push origin main
```

---

# 16. Step 15 — Pull the New Code on EC2

**Run in: `EC2 SSH`.**

Go to the project:

```bash
cd ~/<YOUR-PROJECT-DIRECTORY>
```

Pull the latest code:

```bash
git pull origin main
```

**What it does:** Downloads your newly committed deployment files from GitHub.

Check:

```bash
ls
```

You should now have:

```text
backend/
frontend/
others/
docker-compose.yml
```

---

# 17. Step 16 — Build and Start Docker Services

**Run in: `EC2 SSH`.**

Before starting, validate the Compose configuration:

```bash
docker compose --env-file ./others/.env config
```

**What it does:** Parses the Compose file and reports configuration errors.

If it is valid, build/start:

```bash
docker compose --env-file ./others/.env up -d --build
```

**What it does:**

- `up` → creates/starts services.
- `-d` → runs them in the background.
- `--build` → rebuilds images when needed.

Check service status:

```bash
docker compose --env-file ./others/.env ps
```

Expected conceptually:

```text
NAME        STATUS
backend     running
mysql       running
redis       running
qdrant      running
```

The exact table format may differ depending on Docker Compose version.

---

# 18. Step 17 — Understand the First Docker Startup

The first startup may take time because Docker needs to:

```text
Pull MySQL image
       ↓
Pull Redis image
       ↓
Pull Qdrant image
       ↓
Build backend image
       ↓
Create network
       ↓
Create volumes
       ↓
Start containers
```

Check all logs:

```bash
docker compose --env-file ./others/.env logs
```

Check only backend:

```bash
docker compose --env-file ./others/.env logs backend
```

Follow backend logs live:

```bash
docker compose --env-file ./others/.env logs -f backend
```

Press:

```text
Ctrl + C
```

to stop following the logs. This does **not** stop the container.

---

# 19. Step 18 — Check Individual Services

**Run in: `EC2 SSH`.**

### List containers

```bash
docker compose --env-file ./others/.env ps
```

### MySQL logs

```bash
docker compose --env-file ./others/.env logs mysql
```

### Redis logs

```bash
docker compose --env-file ./others/.env logs redis
```

### Qdrant logs

```bash
docker compose --env-file ./others/.env logs qdrant
```

### Backend logs

```bash
docker compose --env-file ./others/.env logs backend
```

If a service keeps restarting:

```bash
docker compose --env-file ./others/.env ps
```

and then inspect that service's logs.

Do not repeatedly restart without checking the error.

---

# 20. Step 19 — Check Backend Directly

**Run in: `EC2 SSH`.**

Because the backend is intended to be accessible only from the EC2 host, test it from EC2 itself.

For example:

```bash
curl http://127.0.0.1:8000/system/ping
```

**What it does:** Sends a request directly to the FastAPI backend.

Expected behavior:

```text
EC2
 │
 └── curl → 127.0.0.1:8000
                 │
                 ▼
              FastAPI
                 │
                 ▼
           /system/ping
```

If this works, the backend is running.

If it fails, check:

```bash
docker compose --env-file ./others/.env ps
docker compose --env-file ./others/.env logs backend
```

---

# 21. Step 20 — Run Alembic Database Migrations

**Run in: `EC2 SSH`.**

Once the backend and MySQL are running:

```bash
docker compose --env-file ./others/.env exec backend alembic upgrade head
```

**What it does:** Runs the database migrations inside the backend container.

Think of Alembic as:

```text
Code changes
     ↓
Git tracks them

Database structure changes
     ↓
Alembic tracks them
```

Check for migration errors.

Do not continue to frontend/Nginx testing if database migrations fail.

---

# 22. Step 21 — Build the Frontend

The frontend is built into static files that Nginx will serve.

There are two reasonable approaches.

### Recommended for this deployment

Build the frontend on the EC2 server.

**Run in: `EC2 SSH`.**

```bash
cd frontend
npm ci
```

**What it does:** Installs exactly the dependency versions recorded in `package-lock.json`.

Then:

```bash
npm run build
```

**What it does:** Creates the production Vite build.

Expected output:

```text
frontend/
└── dist/
    ├── index.html
    └── assets/
```

Go back to the project root:

```bash
cd ..
```

### Important

The production frontend should use:

```text
VITE_API_URL=/
```

rather than:

```text
http://localhost:8000
```

The relative `/` URL means the browser sends API requests through the same Nginx server.

---

# 23. Step 22 — Install Nginx on EC2

**Run in: `EC2 SSH`.**

Install:

```bash
sudo apt update
sudo apt install nginx -y
```

Check status:

```bash
sudo systemctl status nginx
```

If it is running, Nginx is ready.

If the status screen is open, press:

```text
q
```

to exit.

---

# 24. Step 23 — Create the Frontend Static Directory

**Run in: `EC2 SSH`.**

Create the directory:

```bash
sudo mkdir -p /var/www/pkb
```

**What it does:** Creates the directory where Nginx will serve the React files.

Copy the Vite build:

```bash
sudo rsync -a --delete frontend/dist/ /var/www/pkb/
```

**What it does:**

- Copies the built frontend.
- `--delete` removes old files that are no longer part of the new build.

Check:

```bash
ls /var/www/pkb
```

You should see `index.html` and the assets directory.

---

# 25. Step 24 — Configure Nginx

**Run/edit in: `EC2 SSH` using a terminal editor, or create the configuration locally and copy it to EC2.**

Create a site configuration similar to:

```text
/etc/nginx/sites-available/pkb
```

The configuration needs three important ideas:

### 1. Listen on HTTP

```text
listen 80;
```

### 2. Serve React

Conceptually:

```text
root /var/www/pkb;
```

and use:

```text
try_files $uri /index.html;
```

This fallback is important for React SPA routes.

### 3. Proxy API requests

Conceptually:

```text
/auth       → 127.0.0.1:8000
/files      → 127.0.0.1:8000
/search     → 127.0.0.1:8000
/system     → 127.0.0.1:8000
/documents  → 127.0.0.1:8000
/rag        → 127.0.0.1:8000
```

The overall flow is:

```text
Browser
   │
   ▼
Nginx :80
   │
   ├── "/" and frontend assets
   │       └──► /var/www/pkb
   │
   └── API routes
           │
           └──► 127.0.0.1:8000
                       │
                       ▼
                    FastAPI
```

> This document intentionally shows only the important configuration lines rather than copying the complete Nginx configuration file.

---

# 26. Step 25 — Enable the Nginx Site

**Run in: `EC2 SSH`.**

Create a symbolic link:

```bash
sudo ln -s /etc/nginx/sites-available/pkb /etc/nginx/sites-enabled/pkb
```

Disable the default site if it conflicts:

```bash
sudo rm -f /etc/nginx/sites-enabled/default
```

Test the configuration:

```bash
sudo nginx -t
```

**What it does:** Checks Nginx configuration syntax before reloading.

Only continue if you see a successful configuration test.

Reload:

```bash
sudo systemctl reload nginx
```

**What it does:** Applies the new configuration without unnecessarily stopping Nginx.

---

# 27. Step 26 — Configure Ubuntu Firewall (UFW)

**Run in: `EC2 SSH`.**

The AWS Security Group is the first firewall layer.

UFW provides another firewall layer inside Ubuntu.

Allow SSH:

```bash
sudo ufw allow 22/tcp
```

Allow HTTP:

```bash
sudo ufw allow 80/tcp
```

Reserve HTTPS for Phase 2:

```bash
sudo ufw allow 443/tcp
```

Enable UFW:

```bash
sudo ufw enable
```

Check status:

```bash
sudo ufw status
```

### Important SSH warning

Before enabling UFW, make sure SSH port 22 is allowed.

Otherwise you can accidentally lock yourself out of the server.

Desired result:

```text
Internet
   │
   ├── 22 ──► SSH (restricted at AWS level)
   │
   ├── 80 ──► Nginx
   │
   └── 443 ─► Nginx (Phase 2)
```

Internal:

```text
8000  FastAPI   private
3306  MySQL     private
6379  Redis     private
6333  Qdrant    private
```

---

# 28. Step 27 — First Full Application Test

Open your browser on your Windows PC.

Go to:

```text
http://<ELASTIC-IP>
```

You should see the React application.

The complete request flow should now be:

```text
Windows Browser
       │
       │ http://<ELASTIC-IP>
       ▼
   AWS EC2
       │
       ▼
    Nginx :80
       │
       ├───────────────► React files
       │
       └── API request
               │
               ▼
         FastAPI :8000
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
     MySQL   Redis    Qdrant
                         │
               ┌─────────┴─────────┐
               ▼                   ▼
        Backblaze B2           Gemini
```

---

# 29. Step 28 — Application Smoke Test

A smoke test is a short test to confirm the main application path works.

Test these in order:

### 1. Frontend

```text
http://<ELASTIC-IP>
```

Expected:

```text
React application loads
```

### 2. Backend health

```text
http://<ELASTIC-IP>/system/ping
```

Expected:

```text
Backend responds successfully
```

### 3. Authentication

Test:

```text
Register
Login
Logout
```

### 4. File operations

Test:

```text
Upload
List files
Download
Delete
```

### 5. Knowledge/search flow

Test:

```text
Document processing
Indexing
Semantic search
RAG question
```

### 6. Backblaze B2

Confirm that uploaded files actually reach B2.

### 7. Qdrant

Confirm that documents are indexed and search results are returned.

---

# 30. Step 29 — Basic Docker Commands You Should Know

**Run these in: `EC2 SSH`.**

You do not need to memorize every Docker command.

### Show running containers

```bash
docker ps
```

### Show all containers

```bash
docker ps -a
```

### Compose service status

```bash
docker compose --env-file ./others/.env ps
```

### Start services

```bash
docker compose --env-file ./others/.env up -d
```

### Build and start

```bash
docker compose --env-file ./others/.env up -d --build
```

### Stop services

```bash
docker compose --env-file ./others/.env stop
```

**Important:** `stop` stops containers but does not remove them.

### Start previously stopped services

```bash
docker compose --env-file ./others/.env start
```

### Restart services

```bash
docker compose --env-file ./others/.env restart
```

### Stop and remove containers/network

```bash
docker compose --env-file ./others/.env down
```

This does **not** normally remove named volumes unless you explicitly ask Docker to remove them.

### View logs

```bash
docker compose --env-file ./others/.env logs
```

### Backend logs

```bash
docker compose --env-file ./others/.env logs backend
```

### Follow backend logs

```bash
docker compose --env-file ./others/.env logs -f backend
```

### Execute a command inside backend container

```bash
docker compose --env-file ./others/.env exec backend <command>
```

Example:

```bash
docker compose --env-file ./others/.env exec backend alembic upgrade head
```

### Check Docker disk usage

```bash
docker system df
```

**What it does:** Shows how much disk space Docker images, containers, and volumes use.

> **Warning:** Do not randomly use commands such as `docker system prune --volumes` on a production server. They can delete unused Docker data and potentially remove data you still need.

---

# 31. Step 30 — Basic Nginx Commands

**Run in: `EC2 SSH`.**

Check configuration:

```bash
sudo nginx -t
```

Reload after configuration changes:

```bash
sudo systemctl reload nginx
```

Restart Nginx:

```bash
sudo systemctl restart nginx
```

Check status:

```bash
sudo systemctl status nginx
```

View recent Nginx error logs:

```bash
sudo tail -n 50 /var/log/nginx/error.log
```

View access logs:

```bash
sudo tail -n 50 /var/log/nginx/access.log
```

---

# 32. Step 31 — Basic EC2 Resource Checks

**Run in: `EC2 SSH`.**

Check memory:

```bash
free -h
```

Check disk:

```bash
df -h
```

Check CPU/process usage:

```bash
top
```

Exit `top` with:

```text
q
```

Check swap:

```bash
swapon --show
```

Because this is a small EC2 instance, regularly watch:

```text
RAM
Swap
Disk
CPU
```

---

# 33. Step 32 — What to Do When Something Fails

Do not immediately destroy the server or rebuild everything.

Use this troubleshooting order.

## Case 1 — Website does not open

Check:

```bash
sudo systemctl status nginx
```

Then:

```bash
sudo nginx -t
```

Then:

```bash
sudo tail -n 50 /var/log/nginx/error.log
```

Also check AWS Security Group:

```text
Port 80 → allowed?
```

---

## Case 2 — Frontend opens but API fails

Check backend:

```bash
docker compose --env-file ./others/.env ps
```

Then:

```bash
docker compose --env-file ./others/.env logs backend
```

Test backend directly:

```bash
curl http://127.0.0.1:8000/system/ping
```

If direct backend access works but browser API calls fail, investigate Nginx routing/CORS/frontend configuration.

---

## Case 3 — Backend container keeps restarting

Run:

```bash
docker compose --env-file ./others/.env ps
docker compose --env-file ./others/.env logs backend
```

Look for:

```text
Python import errors
Missing environment variables
Database connection errors
Incorrect paths
Dependency errors
```

---

## Case 4 — Backend cannot connect to MySQL

Check:

```bash
docker compose --env-file ./others/.env ps
docker compose --env-file ./others/.env logs mysql
```

Verify the backend uses:

```text
mysql:3306
```

not:

```text
localhost:3306
```

---

## Case 5 — Backend cannot connect to Redis

Verify:

```text
redis:6379
```

not:

```text
localhost:6379
```

Check:

```bash
docker compose --env-file ./others/.env logs redis
```

---

## Case 6 — Backend cannot connect to Qdrant

Verify:

```text
qdrant:6333
```

not:

```text
localhost:6333
```

Check:

```bash
docker compose --env-file ./others/.env logs qdrant
```

---

## Case 7 — Database migration fails

Run:

```bash
docker compose --env-file ./others/.env logs backend
```

Then:

```bash
docker compose --env-file ./others/.env exec backend alembic upgrade head
```

Check the database connection and migration error before changing anything.

---

# 34. Step 33 — Updating the Application Later

Phase 1 uses **manual deployment**.

When you change code on Windows:

### LOCAL CMD

```cmd
git add .
git commit -m "Update application"
git push origin main
```

Then connect to EC2.

### EC2 SSH

```bash
cd ~/<YOUR-PROJECT-DIRECTORY>
git pull origin main
```

Rebuild backend if backend code/dependencies changed:

```bash
docker compose --env-file ./others/.env up -d --build backend
```

Run migrations if the database schema changed:

```bash
docker compose --env-file ./others/.env exec backend alembic upgrade head
```

If frontend code changed:

```bash
cd frontend
npm ci
npm run build
cd ..
sudo rsync -a --delete frontend/dist/ /var/www/pkb/
```

Reload Nginx if its configuration changed:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Then test:

```text
http://<ELASTIC-IP>
```

---

# 35. Step 34 — Data Persistence and What `docker compose down` Means

This distinction is important for a fresher.

### Restart

```bash
docker compose --env-file ./others/.env restart
```

```text
Containers
   ↓
Restart
   ↓
Data remains
```

### Stop

```bash
docker compose --env-file ./others/.env stop
```

```text
Containers
   ↓
Stopped
   ↓
Data remains
```

### Down

```bash
docker compose --env-file ./others/.env down
```

```text
Containers
   ↓
Removed
   ↓
Named volumes normally remain
```

### Dangerous volume removal

Avoid casually running:

```bash
docker compose --env-file ./others/.env down -v
```

`-v` asks Compose to remove named volumes.

For this project that can mean deleting:

```text
mysql_data
redis_data
qdrant_data
```

and therefore losing persistent application data.

> **Never use `down -v` on the production server unless you intentionally understand and have backed up the data.**

---

# 36. Step 35 — Backup Reminder

Phase 1 should have at least a basic backup procedure.

Remember:

```text
Docker volume ≠ backup
```

A volume protects data from normal container replacement.

A backup protects against:

```text
Server failure
Disk failure
Accidental deletion
Corruption
Bad migration
Operator mistake
```

At minimum, plan backups for:

```text
MySQL
Qdrant
Important configuration
```

Backblaze B2 already provides external object storage for application files.

Detailed automated backup procedures can be added in Phase 2.

---

# 37. Step 36 — Phase 1 Completion Checklist

Phase 1 is complete when all of these are true.

## AWS

- [ ] EC2 Ubuntu instance running.
- [ ] Elastic IP associated.
- [ ] SSH works.
- [ ] Security Group configured.
- [ ] No public MySQL port.
- [ ] No public Redis port.
- [ ] No public Qdrant port.
- [ ] No public FastAPI `8000` port.

## EC2

- [ ] Ubuntu updated.
- [ ] Swap configured.
- [ ] Docker installed.
- [ ] Docker Compose works.
- [ ] UFW configured.

## Docker

- [ ] `backend` container running.
- [ ] `mysql` container running.
- [ ] `redis` container running.
- [ ] `qdrant` container running.
- [ ] Persistent volumes created.
- [ ] Backend can reach MySQL.
- [ ] Backend can reach Redis.
- [ ] Backend can reach Qdrant.

## Backend

- [ ] Gunicorn installed.
- [ ] FastAPI starts successfully.
- [ ] `/system/ping` works.
- [ ] Alembic migrations succeed.
- [ ] Production `.env` is on the server.
- [ ] Production `.env` is not committed to Git.

## Frontend

- [ ] `npm ci` succeeds.
- [ ] `npm run build` succeeds.
- [ ] `frontend/dist` exists.
- [ ] Nginx serves the frontend.
- [ ] Frontend uses `/` as the production API base URL.

## Nginx

- [ ] Nginx installed.
- [ ] Configuration passes `nginx -t`.
- [ ] Frontend is served from `/var/www/pkb`.
- [ ] API routes proxy to FastAPI.
- [ ] React SPA fallback works.

## Application

- [ ] Website loads through Elastic IP.
- [ ] Login works.
- [ ] File upload works.
- [ ] File processing works.
- [ ] Search works.
- [ ] RAG works.
- [ ] Backblaze B2 works.
- [ ] Qdrant indexing/search works.

---

# 38. Final Phase 1 Architecture

At the end of Phase 1, your server should look conceptually like this:

```text
                         INTERNET
                            │
                            │ HTTP :80
                            ▼
                  ┌──────────────────┐
                  │      NGINX       │
                  │                  │
                  │ React static     │
                  │ API reverse      │
                  │ proxy            │
                  └────────┬─────────┘
                           │
                           │ 127.0.0.1:8000
                           ▼
                  ┌──────────────────┐
                  │ FastAPI Backend  │
                  │ Gunicorn         │
                  │ + Uvicorn        │
                  └────────┬─────────┘
                           │
               ┌───────────┼───────────┐
               │           │           │
               ▼           ▼           ▼
          ┌────────┐  ┌────────┐  ┌──────────┐
          │ MySQL  │  │ Redis  │  │ Qdrant   │
          │ :3306  │  │ :6379  │  │ :6333    │
          └────────┘  └────────┘  └──────────┘
               │           │           │
               └───────────┴───────────┘
                     Docker Network
                     PRIVATE ONLY

                     Backend
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
       Backblaze B2          Google Gemini
       Object Storage        AI / Embeddings
```

---

# 39. Phase 1 Mental Model

If you are a fresher, you do **not** need to memorize every command.

Remember these relationships:

```text
EC2
│
│  Cloud computer
│
├── Nginx
│     │
│     ├── Serves React
│     └── Sends API requests to FastAPI
│
└── Docker
      │
      └── Docker Compose
            │
            ├── FastAPI
            ├── MySQL
            ├── Redis
            └── Qdrant
```

And remember the deployment order:

```text
Windows PC
    │
    │ git push
    ▼
GitHub
    │
    │ manual git pull
    ▼
EC2
    │
    ├── Prepare Ubuntu
    ├── Install Docker
    ├── Start containers
    ├── Run migrations
    ├── Build React
    ├── Configure Nginx
    └── Test application
              │
              ▼
       http://<ELASTIC-IP>
```

**Phase 1 goal:**

> **Make the application work reliably on one EC2 server first.**

Do not worry about CI/CD, domain names, HTTPS, automatic deployment, advanced monitoring, or enterprise infrastructure yet.

Those belong to **Phase 2**.
