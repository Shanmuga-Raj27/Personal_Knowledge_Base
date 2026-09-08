# Phase 2 — Production Automation & Advanced Setup Guide

> **Project:** Personal Knowledge Base  
> **Target:** AWS EC2 + Ubuntu + Docker Compose + Nginx + GitHub Actions + Let's Encrypt  
> **Developer machine:** Windows 10 + VS Code CMD terminal + Docker Desktop  
> **Prerequisite:** Phase 1 is complete. The application already works at `http://<ELASTIC-IP>`.  
> **Goal:** Automate deployments, connect a custom domain, enable HTTPS, add basic monitoring, protect secrets, create backups, and prepare a safe rollback process.
>
> **Important:** This guide does **not** contain real passwords, API keys, access keys, private keys, or other secrets. Use placeholders only. Real application secrets stay on the EC2 server, and deployment credentials are stored only in GitHub Secrets.

---

# 1. Before You Start

Phase 2 builds on Phase 1. Do **not** start Phase 2 if the Phase 1 application is unstable.

At the beginning of Phase 2, your server should look like this:

```text
                         AWS EC2 (Ubuntu)
                                │
                ┌───────────────┴───────────────┐
                │                               │
              Nginx                         Docker Compose
             :80 HTTP                            │
                │                  ┌────────────┼────────────┐
                │                  │            │            │
                │               backend       mysql        redis
                │                  │
                │                  └────────────── qdrant
                │
                ▼
         /var/www/pkb
        React static files
```

Phase 2 adds:

```text
Custom domain
      │
      ▼
DNS
      │
      ▼
Elastic IP
      │
      ▼
Nginx :80 / :443
      │
      ├── HTTP → HTTPS redirect
      └── HTTPS → React + FastAPI

GitHub
   │
   ▼
GitHub Actions
   │
   ├── Test
   ├── Build
   ├── SSH
   └── Deploy
```

## Terminal / console contexts used in this guide

| Label | Where you run it | Typical prompt |
| :--- | :--- | :--- |
| **LOCAL CMD** | VS Code → Terminal → Command Prompt on Windows 10 | `C:\Users\YourName\project>` |
| **EC2 SSH** | SSH session connected to Ubuntu EC2 | `ubuntu@ip-xxx:~$` |
| **GITHUB WEB** | GitHub website in your browser | — |
| **AWS CONSOLE** | AWS website in your browser | — |
| **DOMAIN DNS** | Your domain registrar / DNS provider | — |

> **Important:** Commands containing `sudo`, `apt`, `docker`, `systemctl`, `curl`, or `chmod` in the server sections are normally run in **EC2 SSH**.

---

# 2. Step 1 — Create a Dedicated SSH Key for GitHub Actions

## Why do we need another SSH key?

In Phase 1, you used your personal EC2 `.pem` key.

GitHub Actions also needs SSH access to EC2.

Do **not** give your personal `.pem` key to GitHub Actions.

Instead:

```text
Personal SSH key
       │
       └── Your manual EC2 access

Deploy SSH key
       │
       └── GitHub Actions → EC2
```

This is safer because the automation key can be removed without replacing your personal key.

---

## 2.1 Generate the deployment key

**Run in: `LOCAL CMD`.**

```cmd
ssh-keygen -t ed25519 -f id_pkb_deploy -C "github-actions-deploy"
```

This creates:

```text
id_pkb_deploy
id_pkb_deploy.pub
```

The files mean:

```text
id_pkb_deploy
      │
      └── PRIVATE KEY
          Keep secret.
          GitHub Actions uses this.

id_pkb_deploy.pub
      │
      └── PUBLIC KEY
          Safe to install on EC2.
```

When asked for a passphrase, automation normally needs a key that can be used non-interactively. Follow your GitHub Actions/SSH setup policy rather than putting a passphrase into this documentation.

> Never commit `id_pkb_deploy` to Git.

---

## 2.2 Add the public key to EC2

**Run in: `EC2 SSH`.**

Create the SSH directory if necessary:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
```

Add the **contents** of `id_pkb_deploy.pub` to:

```text
~/.ssh/authorized_keys
```

Then:

```bash
chmod 600 ~/.ssh/authorized_keys
```

The important idea is:

```text
LOCAL
id_pkb_deploy.pub
        │
        │ copy public key
        ▼
EC2
~/.ssh/authorized_keys
```

Do not paste the private key into `authorized_keys`.

---

## 2.3 Test the deployment key

**Run in: `LOCAL CMD`.**

```cmd
ssh -i "C:\path\to\id_pkb_deploy" ubuntu@<ELASTIC-IP> "echo key-works"
```

Expected:

```text
key-works
```

If this works, GitHub Actions should be able to use the same private key later.

---

# 3. Step 2 — Store Deployment Credentials in GitHub

**Run in: `GITHUB WEB`.**

Open:

```text
GitHub repository
→ Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

Create these deployment secrets:

| Secret | Purpose |
| :--- | :--- |
| `EC2_HOST` | EC2 Elastic IP |
| `EC2_USER` | Ubuntu SSH username |
| `EC2_SSH_KEY` | Private deployment SSH key |

The flow is:

```text
GitHub Actions
      │
      │ reads encrypted GitHub Secrets
      ▼
SSH connection
      │
      ▼
EC2
```

### Important security rule

GitHub Actions should receive only the credentials needed to **deploy**.

It should not receive:

```text
Gemini API key
Backblaze B2 key
MySQL password
JWT SECRET_KEY
```

Those application secrets remain on the server.

```text
Application secrets
        │
        └── EC2 server .env

Deployment secrets
        │
        └── GitHub Secrets
```

---

# 4. Step 3 — Understand What CI/CD Will Do

Before creating GitHub Actions, understand the manual deployment from Phase 1.

Previously:

```text
Windows
   │
   │ git push
   ▼
GitHub
   │
   │ manually SSH
   ▼
EC2
   │
   ├── git pull
   ├── docker compose build
   ├── restart backend
   ├── run migrations
   ├── npm build
   ├── copy frontend
   ├── reload Nginx
   └── test /system/ping
```

Phase 2 automates this:

```text
Windows PC
    │
    │ git push origin main
    ▼
  GitHub
    │
    ▼
GitHub Actions
    │
    ├── 1. Test backend
    ├── 2. Build frontend
    │
    │ only if successful
    ▼
  SSH to EC2
    │
    ├── 3. git pull
    ├── 4. rebuild/restart backend
    ├── 5. run migrations
    ├── 6. build frontend
    ├── 7. copy frontend
    ├── 8. reload Nginx
    └── 9. health check
             │
             ▼
          SUCCESS
```

## What is CI/CD?

### CI — Continuous Integration

Every code push can automatically:

```text
Run tests
   +
Build application
```

### CD — Continuous Deployment

If the tests pass:

```text
Deploy the new version to EC2
```

So your normal workflow becomes:

```text
Code
 ↓
git commit
 ↓
git push
 ↓
GitHub Actions
 ↓
Test
 ↓
Deploy
 ↓
Health check
```

---

# 5. Step 4 — Create the GitHub Actions Workflow

**Create/edit in: `LOCAL CMD + VS Code editor`.**

Create:

```text
.github/
└── workflows/
    └── deploy.yml
```

The workflow should have two major jobs:

```text
GitHub Actions
│
├── Job 1: Test & Build
│     ├── Checkout repository
│     ├── Install Python
│     ├── Run backend tests
│     ├── Install Node.js
│     ├── npm ci
│     └── npm run build
│
└── Job 2: Deploy
      │
      └── runs only if Job 1 passes
          ├── SSH to EC2
          ├── git pull
          ├── Docker rebuild
          ├── migrations
          ├── frontend build
          ├── Nginx reload
          └── health check
```

### Important workflow settings

The workflow should run when code is pushed to:

```text
main
```

It is also useful to allow:

```text
workflow_dispatch
```

so you can manually start the workflow from GitHub when needed.

Use deployment concurrency so two deployments do not modify production simultaneously.

Conceptually:

```text
Push A ──► Deploy ──► finish
Push B ──► waits
              │
              ▼
           Deploy
```

---

## 5.1 Important workflow commands

The exact workflow YAML belongs in:

```text
.github/workflows/deploy.yml
```

Important commands used by the workflow include:

```text
pytest
```

Runs backend tests.

```text
npm ci
```

Installs frontend dependencies using the committed lockfile.

```text
npm run build
```

Creates the production React bundle.

On EC2:

```text
git pull origin main
```

Downloads the latest committed code.

```text
docker compose up -d --build backend
```

Rebuilds and restarts the backend container.

```text
docker compose exec backend alembic upgrade head
```

Runs database migrations.

```text
sudo rsync -a --delete frontend/dist/ /var/www/pkb/
```

Copies the new frontend bundle to Nginx.

```text
sudo nginx -t
```

Checks Nginx configuration.

```text
sudo systemctl reload nginx
```

Reloads Nginx without unnecessarily stopping the server.

```text
curl -fsS http://127.0.0.1:8000/system/ping
```

Checks that FastAPI is alive.

---

## 5.2 Why `needs: test` matters

The deploy job should depend on the test job.

Conceptually:

```text
Test & Build
     │
     ├── FAIL ──► STOP
     │
     └── PASS
           │
           ▼
        Deploy
```

This prevents an obviously broken build from automatically reaching production.

---

## 5.3 Commit the workflow

**Run in: `LOCAL CMD`.**

```cmd
git add .github/workflows/deploy.yml
git commit -m "Add GitHub Actions deployment"
git push origin main
```

---

# 6. Step 5 — Test the First Automatic Deployment

**Run/check in: `GITHUB WEB`.**

Open:

```text
GitHub repository
→ Actions
```

You should see the workflow run.

Expected:

```text
Test & Build
     │
     │ PASS
     ▼
Deploy to EC2
     │
     │ PASS
     ▼
Health check
     │
     ▼
SUCCESS
```

The final health check should confirm the backend is responding.

For example:

```text
/system/ping
```

If the workflow fails:

1. Open the failed workflow.
2. Open the failed job.
3. Find the **first actual error**.
4. Fix that error.
5. Push again.

Do not focus only on the final error line because later errors can be caused by the first failure.

---

# 7. Step 6 — Automate the "Update App" Flow

After CI/CD works, normal deployment becomes much simpler.

**Run in: `LOCAL CMD`.**

```cmd
git add .
git commit -m "Update application"
git push origin main
```

Then:

```text
GitHub
   │
   ▼
GitHub Actions
   │
   ├── Test
   ├── Build
   ├── Deploy
   └── Health check
```

You normally no longer need to manually SSH into EC2 for every code change.

### Phase 1 vs Phase 2

```text
PHASE 1

git push
   ↓
SSH manually
   ↓
git pull
   ↓
build
   ↓
restart
   ↓
test


PHASE 2

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

This is the main benefit of CI/CD.

---

# 8. Step 7 — Connect Your Custom Domain

A domain changes the public URL from:

```text
http://<ELASTIC-IP>
```

to something like:

```text
https://example.com
```

A domain also makes HTTPS possible with Let's Encrypt.

---

## 8.1 Buy/use a domain

You can use a domain from any registrar/DNS provider that lets you manage DNS records.

For this guide we use:

```text
example.com
www.example.com
```

Replace these placeholders with your actual domain.

---

## 8.2 Create DNS records

**Run in: `DOMAIN DNS`.**

Create:

| Type | Name | Value | Purpose |
| :--- | :--- | :--- | :--- |
| `A` | `@` | `<ELASTIC-IP>` | Root domain |
| `A` | `www` | `<ELASTIC-IP>` | `www` subdomain |

The flow becomes:

```text
Browser
   │
   │ example.com
   ▼
DNS
   │
   │ A record
   ▼
<ELASTIC-IP>
   │
   ▼
EC2
   │
   ▼
Nginx
```

---

## 8.3 Check DNS from Windows

**Run in: `LOCAL CMD`.**

```cmd
nslookup example.com
```

The returned IP should eventually match your Elastic IP.

You can also check:

```cmd
nslookup www.example.com
```

Do not continue to Certbot until the DNS records resolve correctly.

---

# 9. Step 8 — Update Nginx for the Domain

**Run/edit in: `EC2 SSH`.**

Open the Nginx configuration:

```bash
sudo nano /etc/nginx/sites-available/pkb
```

Change the server name from the Phase 1 catch-all:

```text
server_name _;
```

to:

```text
server_name example.com www.example.com;
```

Then test:

```bash
sudo nginx -t
```

If the test succeeds:

```bash
sudo systemctl reload nginx
```

Now Nginx knows that it should serve requests for your domain.

---

# 10. Step 9 — Enable HTTPS with Let's Encrypt

## What is HTTPS?

Without HTTPS:

```text
Browser ── HTTP ──► Server
```

With HTTPS:

```text
Browser ── encrypted HTTPS ──► Server
```

HTTPS protects data travelling between the browser and Nginx.

This is especially important for:

```text
Login credentials
JWT tokens
Uploaded data requests
API requests
```

---

## 10.1 Install Certbot

**Run in: `EC2 SSH`.**

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
```

Certbot is the tool that obtains and manages Let's Encrypt certificates.

---

## 10.2 Request the certificate

**Run in: `EC2 SSH`.**

```bash
sudo certbot --nginx -d example.com -d www.example.com
```

Certbot verifies that the domain points to your server and configures Nginx for HTTPS.

The final request flow becomes:

```text
Browser
   │
   │ HTTPS :443
   ▼
Nginx
   │
   ├── React static files
   │
   └── API proxy
          │
          ▼
       FastAPI :8000
```

HTTP should redirect:

```text
http://example.com
       │
       ▼
https://example.com
```

---

## 10.3 Verify HTTPS from Windows

**Run in: `LOCAL CMD`.**

```cmd
curl https://example.com/system/ping
```

Expected response should indicate that the backend is healthy.

Also open:

```text
https://example.com
```

in your browser.

You should see the browser's secure connection indicator.

---

## 10.4 Test certificate renewal

Let's Encrypt certificates are short-lived, so automatic renewal is important.

**Run in: `EC2 SSH`.**

```bash
sudo certbot renew --dry-run
```

`--dry-run` performs a renewal test without replacing the real certificate.

Check the Certbot timer:

```bash
systemctl list-timers | grep certbot
```

---

# 11. Step 10 — Update the Application for HTTPS

## 11.1 Update CORS

The frontend origin changed from:

```text
http://<ELASTIC-IP>
```

to:

```text
https://example.com
```

If CORS still allows only the old HTTP origin, browsers may block API requests.

**Run/edit in: `EC2 SSH`.**

Open:

```bash
nano ~/<YOUR-PROJECT-DIRECTORY>/others/.env
```

The important idea is:

```text
CORS_ORIGINS = HTTPS domain(s)
```

Do not put real credentials or keys into this guide.

After changing the environment file:

```bash
cd ~/<YOUR-PROJECT-DIRECTORY>
docker compose restart backend
```

Then test:

```bash
curl -fsS https://example.com/system/ping
```

---

## 11.2 Why the frontend should not need a domain-specific API URL

Phase 1 uses:

```text
VITE_API_URL=/
```

This is a relative URL.

So:

```text
Browser loads:
https://example.com

API request:
https://example.com/auth
```

The frontend does not need to know:

```text
EC2 IP
```

or:

```text
example.com
```

This makes future domain changes easier.

---

# 12. Step 11 — Monitoring & Logging

Monitoring answers:

> "Is my application still working?"

For a small EC2 server, start with three things:

```text
1. Container health
2. Memory / CPU
3. Disk usage
```

---

## 12.1 Add Docker health checks

Health checks let Docker test whether a service is responding.

Conceptually:

```text
Container
   │
   ▼
Health check
   │
   ├── healthy
   │
   └── unhealthy
```

For the backend, the health check can call:

```text
/system/ping
```

Use appropriate health checks for MySQL, Redis, Qdrant, and backend.

Also add Docker log limits so logs do not consume the entire disk.

Important configuration concepts:

```yaml
healthcheck:
  interval: 30s
  timeout: 5s
  retries: 3
```

and:

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

These are examples of important settings; keep the complete Compose file in the actual project.

---

## 12.2 Daily server checks

**Run in: `EC2 SSH`.**

```bash
docker compose ps
```

Shows service status.

```bash
docker stats --no-stream
```

Shows current container CPU and memory usage.

```bash
free -h
```

Shows RAM and swap.

```bash
df -h
```

Shows disk usage.

```bash
docker compose logs backend --tail=50
```

Shows recent backend logs.

---

## 12.3 Simple uptime check

Create:

```bash
mkdir -p ~/scripts
nano ~/scripts/uptime-check.sh
```

The script should check:

```text
https://example.com/system/ping
```

and record:

```text
UP
```

or:

```text
DOWN
```

The idea is:

```text
Every 5 minutes
       │
       ▼
/system/ping
       │
   ┌───┴───┐
   │       │
  UP      DOWN
   │       │
   ▼       ▼
 log     investigate
```

Make the script executable:

```bash
chmod +x ~/scripts/uptime-check.sh
```

Then schedule it with cron.

> A local uptime check has one limitation: if the entire EC2 server dies, the check cannot run. An external monitor is better for real availability monitoring.

---

## 12.4 Optional external monitoring

A free external uptime service can request:

```text
https://example.com/system/ping
```

from outside AWS.

This gives you:

```text
Your EC2
    │
    └── DOWN

External monitor
    │
    └── detects DOWN
          │
          ▼
        Alert
```

This is more useful than relying only on a cron job running on the same server.

---

# 13. Step 12 — Secret Management

Keep two categories separate.

```text
                    SECRETS
                       │
             ┌─────────┴─────────┐
             │                   │
       Application           Deployment
             │                   │
             ▼                   ▼
       EC2 server .env      GitHub Secrets
```

## Application secrets

Examples:

```text
SECRET_KEY
MySQL passwords
B2 credentials
Gemini API key
```

Store them only on the EC2 server's environment/configuration.

## Deployment secrets

Examples:

```text
EC2_HOST
EC2_USER
EC2_SSH_KEY
```

Store them in GitHub repository secrets.

### Never put secrets in:

```text
Git repository
README
Markdown documentation
Dockerfile
Frontend source
Frontend bundle
GitHub Actions logs
Screenshots
```

---

## 13.1 Secret rotation

If a third-party key is compromised:

```text
Create new key
      │
      ▼
Update server .env
      │
      ▼
Restart backend
      │
      ▼
Test application
      │
      ▼
Revoke old key
```

Do not revoke the old key before confirming the new key works.

---

## 13.2 JWT secret rotation

If the application's JWT signing secret is suspected to be exposed:

```text
Generate new secret
       ↓
Update server .env
       ↓
Restart backend
       ↓
Existing JWTs become invalid
       ↓
Users log in again
```

This is a security action, not an ordinary deployment.

---

# 14. Step 13 — Backups & Recovery

This is one of the most important Phase 2 concepts.

A Docker volume is **not** the same as a backup.

```text
Docker volume
    │
    └── protects data when a container is recreated

Backup
    │
    └── protects against:
        • server failure
        • disk failure
        • corruption
        • accidental deletion
        • bad migrations
```

---

## 14.1 MySQL backup

**Run in: `EC2 SSH`.**

Create backup directories:

```bash
sudo mkdir -p /var/backups/pkb/mysql
```

Create a compressed MySQL dump using the database credentials already configured on the server.

Conceptually:

```text
MySQL container
      │
      ▼
mysqldump
      │
      ▼
.gz backup file
      │
      ▼
/var/backups/pkb/mysql/
```

A typical backup file looks like:

```text
db_YYYY-MM-DD_HHMM.sql.gz
```

Check backups:

```bash
ls -la /var/backups/pkb/mysql/
```

---

## 14.2 Schedule daily MySQL backups

Use `cron` on EC2.

The goal is:

```text
Every day at 2:00 AM
        │
        ▼
MySQL dump
        │
        ▼
Compressed backup
```

Keep approximately:

```text
7–14 days
```

of backups, depending on your available disk space.

> Before relying on backups, actually test restoring one.

---

## 14.3 Test MySQL restore

A backup is useful only if it can be restored.

Conceptually:

```text
backup.sql.gz
      │
      ▼
gunzip
      │
      ▼
MySQL
      │
      ▼
restored database
```

Do the first restore test using a safe test database/environment whenever possible.

Do not overwrite production data while learning the restore procedure.

---

# 15. Step 13.4 — Qdrant Backup

Qdrant stores vector data.

The important relationship is:

```text
Documents
    │
    ▼
Embeddings
    │
    ▼
Qdrant
```

If Qdrant data is lost, the application may need to re-index documents.

Qdrant supports collection snapshots.

The general process is:

```text
Qdrant collection
       │
       ▼
Snapshot
       │
       ▼
Backup directory
       │
       ▼
Off-server storage
```

Keep the actual snapshot/restore commands aligned with the Qdrant version used by your project.

---

# 16. Step 13.5 — Redis Backup

Redis is primarily used as a cache in this project.

That means Redis data may be less critical than MySQL.

Conceptually:

```text
Redis
  │
  └── cached RAG answers
```

If Redis is lost:

```text
Application
    │
    └── cache becomes empty
```

The application should normally be able to rebuild its cache.

If your production Redis data becomes important, create and test snapshots.

A simple Redis snapshot concept is:

```text
Redis
  │
  ▼
SAVE
  │
  ▼
dump.rdb
```

Do not treat the Redis cache as your primary permanent database.

---

# 17. Step 13.6 — Keep Backups Off the EC2 Server

This is extremely important.

Bad backup design:

```text
EC2
├── Application
└── Backups
```

If EC2's disk is destroyed:

```text
Application ❌
Backups     ❌
```

Better:

```text
EC2
   │
   ├── Application
   └── Local backup
          │
          ▼
       B2 / S3
       or another
       backup location
```

For your project, Backblaze B2 can be used for off-server backup storage.

Keep backup buckets private.

---

# 18. Step 14 — Rollback Strategy

Rollback means:

> "The newest deployment is broken. Return production to the previous known-good version."

The basic strategy is:

```text
Current release
      │
      │ broken
      ▼
Previous known-good release
      │
      ▼
Rollback
```

---

## 18.1 Tag releases

**Run in: `LOCAL CMD`.**

Example:

```cmd
git tag v1.0.0
git push origin v1.0.0
```

After verifying a later release:

```cmd
git tag v1.0.1
git push origin v1.0.1
```

Tags give you named points in Git history.

```text
v1.0.0 ──► known good
   │
   ▼
v1.0.1 ──► known good
   │
   ▼
v1.0.2 ──► broken
```

Rollback:

```text
v1.0.2
  │
  ▼
v1.0.1
```

---

## 18.2 Manual rollback

**Run in: `EC2 SSH`.**

First identify the current commit:

```bash
git rev-parse HEAD
```

Fetch tags:

```bash
git fetch --tags origin
```

Checkout the known-good release:

```bash
git checkout v1.0.1
```

Then rebuild the backend:

```bash
docker compose up -d --build backend
```

Run migrations only when appropriate for the selected release:

```bash
docker compose exec backend alembic upgrade head
```

Rebuild the frontend:

```bash
cd frontend
npm ci
npm run build
cd ..
```

Copy it to Nginx:

```bash
sudo rsync -a --delete frontend/dist/ /var/www/pkb/
```

Reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Finally test:

```bash
curl -fsS https://example.com/system/ping
```

---

## 18.3 Database rollback warning

This is extremely important.

Git rollback and database rollback are **not automatically the same thing**.

Example:

```text
Release v1.0.1
    │
    └── DB schema A

Release v1.0.2
    │
    └── DB schema B
```

If `v1.0.2` changed the database schema, simply checking out `v1.0.1` may not restore the database.

That is why:

```text
Before migration-bearing deployment
          │
          ▼
     DB backup
          │
          ▼
       Deploy
```

If a destructive schema change causes failure, database recovery may require restoring the backup taken before deployment.

### Rollback order

```text
1. Database
       ↓
2. Backend
       ↓
3. Frontend
       ↓
4. Nginx
       ↓
5. Health check
```

Only restore the database when the deployment actually requires it. Do not restore production data unnecessarily.

---

# 19. Step 15 — Verify the Complete Pipeline

**Run first in: `LOCAL CMD`, then check `GITHUB WEB`.**

Make a small and safe application change.

For example:

```text
Change a login-page heading
```

Then:

```cmd
git add .
git commit -m "Test production pipeline"
git push origin main
```

Open:

```text
GitHub
→ Actions
```

Verify:

```text
Test & Build
     │
     ▼
Deploy
     │
     ▼
Health check
     │
     ▼
GREEN
```

Then open:

```text
https://example.com
```

Use:

```text
Ctrl + F5
```

for a hard refresh if the old frontend bundle is cached.

Confirm that your test change is visible.

---

# 20. Final Phase 2 Request Flow

After Phase 2, the complete system should look like this:

```text
                         DEVELOPER
                      Windows 10 PC
                            │
                            │ git push
                            ▼
                         GITHUB
                            │
                            ▼
                  ┌────────────────────┐
                  │   GitHub Actions   │
                  │                    │
                  │  Test backend      │
                  │  Build frontend    │
                  │        │           │
                  │        ▼           │
                  │    SSH Deploy      │
                  └─────────┬──────────┘
                            │
                            │ SSH
                            ▼
                 ┌──────────────────────┐
                 │      AWS EC2         │
                 │       Ubuntu         │
                 │                      │
                 │  ┌────────────────┐  │
Internet ────────►│  │     Nginx      │  │
HTTPS :443        │  │    :80 / :443  │  │
                 │  └───────┬────────┘  │
                 │          │           │
                 │          ▼           │
                 │  /var/www/pkb        │
                 │   React bundle       │
                 │                      │
                 │  ┌────────────────┐  │
                 │  │ Docker Compose  │  │
                 │  │                │  │
                 │  │ backend        │  │
                 │  │ mysql          │  │
                 │  │ redis          │  │
                 │  │ qdrant         │  │
                 │  └────────────────┘  │
                 └──────────┬───────────┘
                            │
                  ┌─────────┴─────────┐
                  ▼                   ▼
             Backblaze B2          Gemini
```

Domain flow:

```text
User
 │
 │ https://example.com
 ▼
DNS
 │
 │ A record
 ▼
Elastic IP
 │
 ▼
EC2
 │
 ▼
Nginx :443
 │
 ├── React static files
 │
 └── API routes
       │
       ▼
    FastAPI
       │
       ├── MySQL
       ├── Redis
       └── Qdrant
```

---

# 21. Phase 2 Mental Model

### Phase 1

```text
Windows PC
    │
    ▼
GitHub
    │
    │ manually SSH
    ▼
EC2
    │
    ├── git pull
    ├── build
    ├── restart
    └── test
```

### Phase 2

```text
Windows PC
    │
    │ git push
    ▼
GitHub
    │
    ▼
GitHub Actions
    │
    ├── test
    ├── build
    └── deploy
           │
           ▼
         EC2
           │
           ├── HTTPS
           ├── monitoring
           ├── backups
           └── rollback
```

The three major improvements are:

```text
1. Automation
   Push code → deployment happens automatically.

2. Security
   Domain + HTTPS → encrypted browser/server traffic.

3. Recovery
   Monitoring + backups + rollback → safer production operation.
```

---

# 22. Phase 2 Completion Checklist

## CI/CD

- [ ] Dedicated deployment SSH key created.
- [ ] Public deployment key installed on EC2.
- [ ] GitHub deployment secrets configured.
- [ ] `deploy.yml` committed.
- [ ] Backend tests pass in GitHub Actions.
- [ ] Frontend build passes in GitHub Actions.
- [ ] Deploy job runs only after tests pass.
- [ ] Backend deployment succeeds.
- [ ] Database migration step succeeds.
- [ ] Frontend deployment succeeds.
- [ ] Nginx reload succeeds.
- [ ] Final health check succeeds.
- [ ] Deployment concurrency prevents overlapping deployments.

## Domain & HTTPS

- [ ] Domain purchased/configured.
- [ ] Root `A` record points to Elastic IP.
- [ ] `www` record points to Elastic IP if used.
- [ ] `nslookup` returns the correct IP.
- [ ] Nginx `server_name` updated.
- [ ] Certbot installed.
- [ ] Let's Encrypt certificate issued.
- [ ] HTTP redirects to HTTPS.
- [ ] HTTPS website opens.
- [ ] HTTPS `/system/ping` works.
- [ ] `certbot renew --dry-run` succeeds.
- [ ] CORS updated to HTTPS domain.

## Monitoring

- [ ] Docker health checks configured.
- [ ] Docker log size limits configured.
- [ ] RAM/swap checked.
- [ ] Disk usage checked.
- [ ] Uptime check configured.
- [ ] External monitoring configured if desired.
- [ ] Basic troubleshooting commands are understood.

## Secrets

- [ ] Application secrets remain on EC2.
- [ ] Deployment secrets remain in GitHub Secrets.
- [ ] No real secrets exist in Git.
- [ ] No secrets are included in documentation.
- [ ] No secrets are embedded into frontend code.
- [ ] Secret rotation procedure is understood.

## Backups

- [ ] MySQL backup created.
- [ ] Daily MySQL backup scheduled.
- [ ] Backup retention configured.
- [ ] Qdrant snapshot procedure understood/tested.
- [ ] Redis recovery procedure understood.
- [ ] At least one restore test completed.
- [ ] Backups copied off the EC2 server.
- [ ] Backup storage is private.

## Rollback

- [ ] Releases are tagged.
- [ ] Previous known-good release identified.
- [ ] Manual rollback procedure tested.
- [ ] Database backup exists before migration-bearing deployments.
- [ ] Database rollback risk is understood.
- [ ] Rollback health check works.

---

# 23. What You Have After Phase 2

You started with:

```text
"It works on my PC."
```

Phase 1 gave you:

```text
"It works on EC2."
```

Phase 2 gives you:

```text
"It can be updated automatically,
accessed securely,
monitored,
backed up,
and rolled back."
```

The final operational workflow is:

```text
                    NORMAL DEVELOPMENT

Windows PC
    │
    │ code change
    ▼
git add
    │
    ▼
git commit
    │
    ▼
git push
    │
    ▼
GitHub
    │
    ▼
GitHub Actions
    │
    ├── Test
    │    └── FAIL → stop
    │
    ├── Build
    │    └── FAIL → stop
    │
    └── Deploy
         │
         ├── SSH → EC2
         ├── Docker rebuild
         ├── Migration
         ├── Frontend build
         ├── Nginx reload
         └── Health check
                  │
                  ▼
               LIVE
```

And when something goes wrong:

```text
Problem
   │
   ├── Check logs
   ├── Check containers
   ├── Check health endpoint
   ├── Check Nginx
   │
   └── If necessary
          │
          ▼
       Rollback
          │
          ▼
     Known-good release
```

> **Final rule:** Keep Phase 2 simple. You do not need Kubernetes, Terraform, microservices, a separate database server, or complex observability for this small MVP. First make this single-EC2 setup reliable. Upgrade the architecture only when the project's traffic, reliability, or team size actually requires it.
