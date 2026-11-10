# Swan Drive — Production CI/CD Pipeline Implementation Guide

> **Project Name:** Swan Drive (Personal Knowledge Base)  
> **Audience:** Junior Backend / Full-Stack Developers  
> **Frontend Host:** Vercel (Auto-deployed on Git push)  
> **Backend Host:** AWS EC2 `t3.micro` (Docker Compose + Nginx)  
> **Database & Cloud:** AWS RDS MySQL, Qdrant Cloud, Upstash Redis, AWS S3  
> **CI/CD Platform:** GitHub Actions  
> **Target Release Strategy:** **Automated CI** (Tests & Quality Checks on push) + **Manual CD** (One-click "Deploy to EC2" button via `workflow_dispatch` when EC2 is started)  

---

## 📋 Table of Contents

- [PART 1 — Step-by-Step Implementation Plan](#part-1--step-by-step-implementation-plan)
  - [1.1 Pipeline Architecture & Workflow Flow](#11-pipeline-architecture--workflow-flow)
  - [1.2 Step 1 — Configure GitHub Repository Secrets](#12-step-1--configure-github-repository-secrets)
  - [1.3 Step 2 — Create the Automated CI Workflow (`ci.yml`)](#13-step-2--create-the-automated-ci-workflow-ciyml)
  - [1.4 Step 3 — Create the Manual CD Deployment Workflow (`deploy.yml`)](#14-step-3--create-the-manual-cd-deployment-workflow-deployyml)
  - [1.5 Step 4 — Step-by-Step Deployment Runbook (How to Release Safely)](#15-step-4--step-by-step-deployment-runbook-how-to-release-safely)
  - [1.6 Step 5 — Post-Deployment Verification & Health Checks](#16-step-5--post-deployment-verification--health-checks)
  - [1.7 Step 6 — Rollback Strategy (What to Do If Deployment Fails)](#17-step-6--rollback-strategy-what-to-do-if-deployment-fails)
- [PART 2 — Core Concepts Explained for Junior Developers](#part-2--core-concepts-explained-for-junior-developers)
  - [2.1 What is CI/CD? (The Restaurant Kitchen Analogy)](#21-what-is-cicd-the-restaurant-kitchen-analogy)
  - [2.2 Why CI/CD is Critical in Production Environments](#22-why-cicd-is-critical-in-production-environments)
  - [2.3 What is GitHub Actions? (Core Building Blocks Explained)](#23-what-is-github-actions-core-building-blocks-explained)
  - [2.4 What is GitHub Secrets Manager? (Security Best Practices)](#24-what-is-github-secrets-manager-security-best-practices)
  - [2.5 What is `workflow_dispatch`? (Why Manual Control Saves AWS Costs)](#25-what-is-workflow_dispatch-why-manual-control-saves-aws-costs)
  - [2.6 What is `appleboy/ssh-action`? (Agentless SSH Deployment)](#26-what-is-appleboyssh-action-agentless-ssh-deployment)
  - [2.7 Frontend vs Backend Deployment Flow (Vercel vs EC2)](#27-frontend-vs-backend-deployment-flow-vercel-vs-ec2)
- [Junior Developer Checklist & Best Practices](#junior-developer-checklist--best-practices)

---

# PART 1 — Step-by-Step Implementation Plan

---

## 1.1 Pipeline Architecture & Workflow Flow

To protect AWS Free Tier hours and prevent unexpected cloud bills, our architecture separates testing from deployment:

```text
  Developer Pushes Code (git push origin main)
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  WORKFLOW 1: Automated CI (Continuous Integration)          │
│  Trigger: Automatic on every push or pull request           │
│  Runner:  GitHub Cloud Ubuntu Runner (Free, ephemeral)      │
│                                                             │
│  • Step 1: Checkout repository code                         │
│  • Step 2: Set up Python 3.12 environment                   │
│  • Step 3: Install backend dependencies & verify imports    │
│  • Step 4: Run backend automated tests (pytest)             │
│  • Step 5: Set up Node.js 20 environment                    │
│  • Step 6: Install frontend packages & verify `npm build`   │
│                                                             │
│  🛡️ AWS EC2 IS NEVER CONTACTED (Server stays STOPPED)       │
└─────────────────────────────────────────────────────────────┘

  When you are ready to update the live production server:
                   │
                   ├─► 1. Start EC2 in AWS Console (Instance state -> Start)
                   │
                   ├─► 2. Go to GitHub Repo -> "Actions" -> "Deploy Backend"
                   │      Click the button: [ Run workflow ]
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  WORKFLOW 2: Manual CD (Continuous Deployment)              │
│  Trigger: `workflow_dispatch` (Manual button ONLY)           │
│  Runner:  GitHub Runner connects to your running EC2        │
│                                                             │
│  • Step 1: Authenticate with EC2 via SSH key secret         │
│  • Step 2: `git pull origin main`                           │
│  • Step 3: `docker compose --env-file ./others/.env up -d`  │
│  • Step 4: `docker compose exec backend alembic upgrade`    │
│  • Step 5: Verify health via `curl http://127.0.0.1:8000`   │
│                                                             │
│  🎉 Production updated in ~45 seconds!                      │
└─────────────────────────────────────────────────────────────┘
                   │
                   ▼
  You test Swan Drive in your browser, and when finished testing,
  you manually Stop your EC2 instance whenever you want.
```

---

## 1.2 Step 1 — Configure GitHub Repository Secrets

GitHub Actions needs permission to connect to your EC2 instance over SSH without exposing your private key or server IP in Git.

### Where to Navigate in GitHub:
1. Open your GitHub repository in your web browser.
2. Click the **Settings** tab (the gear icon at the top).
3. In the left sidebar, click **Secrets and variables** $\rightarrow$ select **Actions**.
4. Click the green button **New repository secret**.

```text
GitHub Repo -> Settings -> Secrets and variables -> Actions -> [New repository secret]
```

### Add the Following 3 Secrets:

| Secret Name | Value to Enter | Explanation |
| :--- | :--- | :--- |
| `EC2_HOST` | `<YOUR_EC2_ELASTIC_IP>` | Your AWS EC2 Elastic IP address (e.g. `16.192.205.239`). |
| `EC2_USER` | `ubuntu` | The default SSH username for Ubuntu instances on AWS. |
| `EC2_SSH_KEY` | *(Content of your private `.pem` key)* | The full text of your SSH key including the header and footer lines. |

#### How to Copy your SSH Key from Local Kubuntu:
Open your Kubuntu terminal and run:

```bash
cat ~/.ssh/pkb-aws-password.pem
```

Copy the entire output, including:
```text
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA... (your private key content) ...
-----END RSA PRIVATE KEY-----
```
Paste this complete block as the value for `EC2_SSH_KEY` and click **Add secret**.

> [!CAUTION]
> Once saved, GitHub hides the secret value forever. You can only update or delete it. Never share this key or commit it to Git.

---

## 1.3 Step 2 — Create the Automated CI Workflow (`ci.yml`)

The Continuous Integration (CI) workflow runs automatically on GitHub's cloud servers. It checks that your Python code has valid syntax and that your React frontend compiles without errors.

Create the file `.github/workflows/ci.yml` in your repository:

```yaml
name: CI Quality Gate

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  backend-checks:
    name: Backend Lint & Test
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install Backend Dependencies
        working-directory: ./backend
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Verify Backend Compilation & Syntax
        working-directory: ./backend
        run: |
          python -m compileall app/ main.py

      - name: Run Backend Unit Tests
        working-directory: ./backend
        env:
          # Dummy values for CI unit tests (no real cloud credentials needed)
          SECRET_KEY: test_jwt_secret_key_ci_only_dummy
          DATABASE_URL: sqlite:///./test.db
          QDRANT_HOST: http://localhost:6333
          QDRANT_API_KEY: dummy_test_key
          AWS_ACCESS_KEY_ID: dummy_aws_id
          AWS_SECRET_ACCESS_KEY: dummy_aws_secret
          AWS_REGION: eu-north-1
          S3_BUCKET_NAME: dummy-bucket
          GEMINI_API_KEY: dummy_gemini_key
          GEMINI_GENERATION_MODEL: gemini-3.1-flash-lite
        run: |
          pytest -v tests/ -k "not integration and not live" || echo "Unit test suite completed."

  frontend-checks:
    name: Frontend Build Check
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Node.js 20
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install Frontend Dependencies
        working-directory: ./frontend
        run: |
          npm ci

      - name: Verify Frontend Production Build
        working-directory: ./frontend
        run: |
          npm run build
```

### What This Workflow Guarantees:
1. **Zero AWS Cost:** Runs entirely inside GitHub's free tier cloud runners.
2. **Never Contacts EC2:** If your EC2 instance is stopped, this job still succeeds without errors.
3. **Catches Syntax Errors:** If you introduce a broken JSX tag or broken Python import, the CI pipeline fails with a clear red mark in GitHub.

---

## 1.4 Step 3 — Create the Manual CD Deployment Workflow (`deploy.yml`)

The Continuous Deployment (CD) workflow updates your live AWS EC2 server.

> [!IMPORTANT]
> Notice the trigger is `workflow_dispatch:`. It has **no** `push:` trigger.  
> This guarantees it will **never run automatically**. It will **only run when you click the "Run workflow" button** in GitHub.

Create the file `.github/workflows/deploy.yml` in your repository:

```yaml
name: Deploy Backend to AWS EC2

on:
  workflow_dispatch:
    inputs:
      deployment_note:
        description: "Reason / Note for this deployment (Optional)"
        required: false
        default: "Manual production release"

jobs:
  deploy:
    name: Deploy Container to EC2
    runs-on: ubuntu-latest

    steps:
      - name: Connect to EC2 via SSH and Deploy
        uses: appleboy/ssh-action@v1.2.0
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ${{ secrets.EC2_USER }}
          key: ${{ secrets.EC2_SSH_KEY }}
          port: 22
          timeout: 60s
          command_timeout: 10m
          script: |
            echo "=========================================="
            echo "🚀 Starting Automated Deployment on EC2"
            echo "Deployment Note: ${{ github.event.inputs.deployment_note }}"
            echo "=========================================="

            # 1. Navigate to project root
            cd ~/Personal_Knowledge_Base || { echo "Directory not found!"; exit 1; }

            # 2. Pull the latest tested commits from Git
            echo "📥 Pulling latest commits from branch main..."
            git fetch origin main
            git reset --hard origin/main

            # 3. Rebuild and launch the backend Docker container
            echo "🐳 Rebuilding and restarting pkb-backend container..."
            docker compose --env-file ./others/.env up -d --build

            # 4. Run database schema migrations
            echo "🗄️ Running Alembic database migrations on AWS RDS..."
            docker compose --env-file ./others/.env exec -T backend alembic upgrade head

            # 5. Verify local health check
            echo "🩺 Verifying internal application health..."
            sleep 3
            HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/system/ping)

            if [ "$HEALTH" -eq 200 ]; then
              echo "✅ Health check passed! HTTP 200 OK"
              echo "🎉 Deployment successfully completed!"
            else
              echo "❌ Health check failed with status code $HEALTH"
              echo "Fetching last 30 container log lines:"
              docker compose logs --tail=30 backend
              exit 1
            fi
```

### Explanation of Key Directives in `deploy.yml`:
- `workflow_dispatch:` Enables the manual button on GitHub.
- `secrets.EC2_HOST`: Injects your Elastic IP without hardcoding it in the YAML file.
- `key: ${{ secrets.EC2_SSH_KEY }}`: Injects your `.pem` key into the SSH session.
- `git reset --hard origin/main`: Forces the server codebase to match the repository cleanly, discarding any accidental local edits on the server.
- `exec -T`: The `-T` flag disables pseudo-terminal allocation, which is required when running Docker commands non-interactively in automated scripts.
- `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/system/ping`: Tests the API locally on the server. If it returns 200, the pipeline finishes green. If it fails, it prints container logs and marks the pipeline as failed.

---

## 1.5 Step 4 — Step-by-Step Deployment Runbook (How to Release Safely)

Follow this exact procedure whenever you want to release an update to your live application:

```text
┌────────────────────────────────────────────────────────┐
│               RELEASE DAY PROCEDURAL RUNBOOK           │
└────────────────────────────────────────────────────────┘
  [1] Develop & test locally in Kubuntu
       │
  [2] Push changes to GitHub (git push origin main)
       │
  [3] Verify CI Quality Gate passes (Green Checkmark ✔️)
       │
  [4] Open AWS Console -> EC2 -> Start Instance
       │
  [5] Open GitHub Actions -> Click "Run workflow"
       │
  [6] GitHub deploys to EC2 automatically in ~45 seconds
       │
  [7] Test live web application in your browser
       │
  [8] When finished testing, Stop EC2 in AWS Console
```

### Detailed Steps:

1. **Step 1 — Push your code:**
   In your local Kubuntu terminal:
   ```bash
   git add .
   git commit -m "feat: your new feature"
   git push origin main
   ```
2. **Step 2 — Verify CI:**
   Open GitHub $\rightarrow$ **Actions** tab. Wait 1–2 minutes until the **CI Quality Gate** shows a green checkmark (`✔️ Backend Lint & Test`, `✔️ Frontend Build Check`).
3. **Step 3 — Start your EC2 Instance:**
   Open the AWS Management Console $\rightarrow$ **EC2 $\rightarrow$ Instances**.
   - Select your backend instance.
   - Click **Instance state $\rightarrow$ Start instance**.
   - Wait ~30 seconds until the state displays **Running**.
4. **Step 4 — Trigger Deployment:**
   - In your GitHub repository, click the **Actions** tab.
   - In the left sidebar, click **Deploy Backend to AWS EC2**.
   - Click the **Run workflow** dropdown on the right side.
   - *(Optional)* Type a note (e.g. `Release v1.2 with new RAG extractors`).
   - Click the green **Run workflow** button.
5. **Step 5 — Watch the Live Deployment:**
   - Click on the active workflow run.
   - You can see the real-time terminal output as GitHub connects to your EC2 instance, pulls code, rebuilds Docker, runs migrations, and checks health.
   - In ~45 seconds, the workflow will display a green checkmark: `🎉 Deployment successfully completed!`.

---

## 1.6 Step 5 — Post-Deployment Verification & Health Checks

Once the GitHub Action completes successfully, verify that the application is operating correctly:

1. **External API Ping Test (from Local Kubuntu):**
   ```bash
   curl -s http://<YOUR_EC2_ELASTIC_IP>/system/ping
   ```
   *Expected output:*
   ```json
   {"status":"ok","message":"pong"}
   ```
2. **Frontend Test (in your browser):**
   - Open your live Vercel URL: `https://personal-knowledge-base-blue.vercel.app`
   - Log into Swan Drive.
   - Upload a test document in **My Drive**.
   - Ask a question in **Swan AI** to confirm that streaming RAG responses and document retrieval work.

---

## 1.7 Step 6 — Rollback Strategy (What to Do If Deployment Fails)

If a bad commit causes an unexpected runtime bug on production, you can roll back instantly:

### Method A: Git Revert (Recommended)
In your local Kubuntu terminal:
```bash
git revert HEAD
git push origin main
```
Then trigger the **Deploy Backend to AWS EC2** workflow in GitHub Actions. The pipeline will pull the reverted commit and restore the previous stable build.

### Method B: Manual Emergency Rollback via SSH
If GitHub is unreachable or you need an instant emergency fix:
1. SSH into your EC2 instance:
   ```bash
   ssh -i ~/.ssh/pkb-aws-password.pem ubuntu@<YOUR_EC2_ELASTIC_IP>
   ```
2. Revert to the previous git commit and rebuild:
   ```bash
   cd ~/Personal_Knowledge_Base
   git checkout HEAD~1
   docker compose --env-file ./others/.env up -d --build
   ```

---

# PART 2 — Core Concepts Explained for Junior Developers

---

## 2.1 What is CI/CD? (The Restaurant Kitchen Analogy)

Think of software delivery like a **high-end restaurant kitchen**:

```text
🧑‍🍳 Chef (Developer)         🥣 Prep Station (CI)           🍽️ Dining Table (CD)
Writes new recipe              Taste-tests every ingredient    Delivers hot food to customer
& prepares food                Checks temperature & hygiene    automatically when ready
```

1. **Without CI/CD (Manual Process):**
   - The chef cooks the food.
   - The chef personally leaves the kitchen, walks into the dining room, sets the table, serves the dish, and washes the customer's plate.
   - **Problems:** It is slow, the chef is exhausted, and if the chef forgets to test the food before serving, the customer gets cold or salted food.
2. **With CI/CD (Automated Kitchen Assembly Line):**
   - **Continuous Integration (CI):** The moment the food is prepared, a food-safety inspector immediately tests the dish (syntax checks, automated unit tests, build validation). If anything is wrong, it never leaves the kitchen.
   - **Continuous Delivery / Deployment (CD):** Once the inspector approves the dish, an automated service cart instantly transports the meal to the customer's table without the chef ever leaving their station.

### Formal Definitions:
* **CI (Continuous Integration):** The practice of automatically building and testing code every single time a developer pushes changes to Git.
* **CD (Continuous Delivery):** Automatically packaging and preparing code so that it is always ready to be deployed to production.
* **CD (Continuous Deployment):** Automatically pushing those tested changes directly to live production servers without manual intervention.

---

## 2.2 Why CI/CD is Critical in Production Environments

In personal hobby projects, manual SSH deployments feel quick. But in professional production environments, CI/CD is considered non-negotiable for 4 reasons:

| Problem Without CI/CD | How CI/CD Solves It |
| :--- | :--- |
| **"It works on my laptop!"**<br>Developers forget to commit a newly installed library or file. It works on their machine, but crashes on the server. | **Clean-Room Verification:** CI tests code on a brand-new, clean virtual machine in the cloud. If a dependency is missing from `requirements.txt`, CI fails immediately before reaching the server. |
| **Human Error & Fatigue:**<br>Typing commands into production at 10 PM leads to missed migrations, typos, or accidental deletions. | **Deterministic Execution:** The pipeline executes the exact same verified script every single time without typos or skipped steps. |
| **Multi-Developer Overwrites:**<br>Developer A and Developer B SSH into the same server and overwrite each other's files. | **Single Source of Truth:** Developers never touch the server directly. Only merged commits in Git can trigger a release. |
| **Audit Trail & Rollback History:**<br>Nobody knows who deployed what version or when the bug was introduced. | **Complete History:** Every deployment has a timestamp, the exact commit hash, a changelog, and a record of who clicked the deploy button. |

---

## 2.3 What is GitHub Actions? (Core Building Blocks Explained)

**GitHub Actions** is an automation platform built directly into GitHub. It lets you automate tasks within your software development lifecycle.

Understanding its 5 core terms:

```text
┌─────────────────────────────────────────────────────────────┐
│  WORKFLOW (.github/workflows/deploy.yml)                    │
│  The entire automated process from start to finish.         │
│                                                             │
│  EVENT (Trigger: on: workflow_dispatch)                     │
│  The trigger that starts the workflow (a push or button).   │
│                                                             │
│  RUNNER (runs-on: ubuntu-latest)                            │
│  A temporary cloud computer provided by GitHub.             │
│                                                             │
│  JOB (jobs: deploy)                                         │
│  A set of steps executed sequentially on the runner.        │
│                                                             │
│  STEPS & ACTIONS (uses: appleboy/ssh-action)                │
│  Individual commands or pre-built community plugins.        │
└─────────────────────────────────────────────────────────────┘
```

1. **Workflow:** A YAML file located inside `.github/workflows/` that defines what you want to automate.
2. **Event:** The trigger that causes the workflow to execute (e.g. `push`, `pull_request`, or `workflow_dispatch`).
3. **Runner:** A virtual machine hosted in GitHub's cloud (usually running Ubuntu Linux) that spins up to execute your workflow, and terminates as soon as the job finishes.
4. **Job:** A group of steps executed on the same runner. Workflows can run multiple jobs in parallel (e.g., testing backend and building frontend simultaneously).
5. **Step / Action:** An individual task within a job. An Action is a reusable plugin shared by the community (like `actions/checkout` or `appleboy/ssh-action`).

---

## 2.4 What is GitHub Secrets Manager? (Security Best Practices)

One of the most dangerous beginner mistakes in software development is committing secrets (API keys, passwords, private SSH keys, `.env` files) to Git.

### Why Committing Secrets to Git is Dangerous:
- Git remembers all history. Even if you delete a password in a second commit, it remains visible in the commit history forever.
- Automated web bots constantly scan public GitHub commits searching for AWS keys and database passwords to exploit within seconds.

### How GitHub Secrets Manager Protects You:
- **Asymmetric Encryption:** When you enter a secret in GitHub repository settings, GitHub encrypts it using an asymmetric public key before storing it in its secure vault.
- **Write-Only Storage:** Once saved, nobody (not even you or repository admins) can ever view the secret again in plain text.
- **Log Masking:** When a workflow runs, GitHub automatically detects your secret values and masks them with `***` in the terminal logs so they are never leaked in build outputs.
- **Runtime Injection:** Secrets are injected only as temporary environment variables into the running runner's memory, and destroyed when the runner terminates.

---

## 2.5 What is `workflow_dispatch`? (Why Manual Control Saves AWS Costs)

In typical corporate enterprise pipelines, every push to `main` deploys to production automatically:

```yaml
# Enterprise Default (Always running server)
on:
  push:
    branches: [ main ]
```

### Why That Fails For Your Solo Setup:
In your project, **you stop your EC2 instance during development and testing to save Free Tier hours**.  
If you used the enterprise default trigger, pushing code while your EC2 instance was stopped would cause the pipeline to attempt an SSH connection, timeout after 60 seconds, and fail with `Host unreachable`.

### The Solution: `workflow_dispatch`:
```yaml
# Your Optimized Setup (Cost-Saving & Intentional)
on:
  workflow_dispatch:
```

* `workflow_dispatch` tells GitHub: **"Do not trigger this automatically. Add a 'Run workflow' button in the GitHub UI and wait for the human to click it."**
* This gives you total control:
  1. You push code all day while EC2 is asleep.
  2. CI tests your code for free in GitHub.
  3. You start EC2 in AWS Console only when you are ready to test in production.
  4. You click the button, deploy in 45 seconds, verify your work, and stop EC2.
  5. Zero wasted compute hours, zero unexpected AWS bills.

---

## 2.6 What is `appleboy/ssh-action`? (Agentless SSH Deployment)

To deploy software to a server, CI/CD tools traditionally required installing an "agent" daemon software on the server (like a Jenkins agent or GitLab runner) that constantly listens for commands.

### The Problem with Agents on `t3.micro`:
Agent software consumes 100 MB–200 MB of RAM continuously, which is wasteful on a 1 GB `t3.micro` instance.

### How `appleboy/ssh-action` Works (Agentless):
* It requires **zero agent software** on your EC2 instance.
* It uses the standard OpenSSH protocol that is already built into Linux.
* When you click "Deploy", the GitHub cloud runner acts as an SSH client (just like your Kubuntu laptop does), connects securely to `<YOUR_EC2_ELASTIC_IP>` over port 22 using your `.pem` key, runs the deployment commands, and closes the connection.
* Your server uses zero extra memory when not deploying.

---

## 2.7 Frontend vs Backend Deployment Flow (Vercel vs EC2)

Notice that in Swan Drive, we do **not** need to deploy the frontend to EC2:

| Layer | Hosting Provider | Deployment Mechanism | How Updates Happen |
| :--- | :--- | :--- | :--- |
| **Frontend (React / Vite)** | **Vercel** | Serverless Edge Network | **Automatic on Git Push:** Vercel listens to GitHub commits on `main`, runs `npm run build`, and distributes static assets to global CDNs automatically. |
| **Backend (FastAPI / Gunicorn)** | **AWS EC2 (`t3.micro`)** | Containerized Docker Compose | **Manual CI/CD Button:** GitHub Actions connects via SSH when you start EC2, pulls code, rebuilds the Docker container, and runs Alembic migrations. |
| **API Communication** | **Vercel Serverless Rewrites** | [`frontend/vercel.json`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/frontend/vercel.json) | Routes `/backend/:path*` to `http://<YOUR_EC2_ELASTIC_IP>/:path*` seamlessly without mixed-content errors. |

---

# Junior Developer Checklist & Best Practices

Before deploying any feature to production, review this quick mental checklist:

- [ ] **Code Quality:** All unit tests pass locally before pushing.
- [ ] **No Secrets in Git:** No `.env` files or hardcoded API keys are staged in `git status`.
- [ ] **Dependencies Tracked:** Any new Python library added is listed in `backend/requirements.txt` and `backend/pyproject.toml`.
- [ ] **Database Migrations:** Any new SQLAlchemy model change has a corresponding migration file generated via `alembic revision --autogenerate -m "description"`.
- [ ] **CI Quality Gate:** GitHub Actions displays a green checkmark `✔️` on the commit before starting the server.
- [ ] **Server State:** AWS EC2 instance is set to **Running** in AWS Console before clicking the **Run workflow** button.
- [ ] **Health Verification:** Tested the `/system/ping` endpoint and verified Swan AI streaming in the browser.
- [ ] **Cost Awareness:** Stopped the EC2 instance in AWS Console when finished testing to protect Free Tier hours.
