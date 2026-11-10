# Phase 1.2 — Cloud-Native Deployment Guide (AWS EC2 t3.micro Free Tier + Vercel Frontend)

> **Application Name:** Swan Drive (Personal Knowledge Base)  
> **Backend Host:** AWS EC2 `t3.micro` (1 vCPU, 1 GB RAM, Ubuntu LTS, AWS Free Tier)  
> **Frontend Host:** Vercel (`https://personal-knowledge-base-blue.vercel.app`)  
> **Managed Cloud Services:**  
> - **Relational Database:** AWS RDS MySQL  
> - **Vector Database:** Qdrant Cloud Cluster  
> - **Cache & Key-Value:** Upstash Redis (Serverless)  
> - **File & Document Storage:** AWS S3 (Secure Storage)  
> - **AI Embeddings & Generation:** Google Gemini API  
> **Developer Local Machine:** Linux Kubuntu (bash terminal)  
> **Target Server:** Existing AWS EC2 instance upgraded from `t3.small` to `t3.micro`  

---

## 📋 Navigation

| # | Step | Purpose | Context |
| :---: | :--- | :--- | :--- |
| — | [Core Concepts: Nginx & UFW Explained](#core-concepts-nginx--ufw-explained) | Understand Nginx reverse proxy, SSE streaming, and UFW firewall | Concepts |
| — | [Terminal Contexts (Kubuntu vs EC2)](#terminal-contexts-kubuntu-vs-ec2) | Clear distinction between your local PC and remote AWS server | Reference |
| 1 | [Step 1 — Resize Existing EC2 Instance to `t3.micro`](#step-1--resize-existing-ec2-instance-to-t3micro) | Switch instance type in AWS Console within Free Tier | AWS Console |
| 2 | [Step 2 — Verify AWS RDS Security Group Inbound Rule](#step-2--verify-aws-rds-security-group-inbound-rule) | Ensure MySQL RDS allows connections from EC2 Elastic IP | AWS Console |
| 3 | [Step 3 — Connect to EC2 from Local Kubuntu](#step-3--connect-to-ec2-from-local-kubuntu) | Establish secure SSH session using your `.pem` key | `LOCAL KUBUNTU` |
| 4 | [Step 4 — Clean Up Old Docker Containers & Reclaim Disk Space](#step-4--clean-up-old-docker-containers--reclaim-disk-space) | Remove legacy local MySQL, Redis, and Qdrant containers/volumes | `EC2 SSH` |
| 5 | [Step 5 — Verify Existing Swap Space on EC2](#step-5--verify-existing-swap-space-on-ec2) | Confirm 2 GB swap is active to protect `t3.micro` memory | `EC2 SSH` |
| 6 | [Step 6 — Pull Latest Code from Git](#step-6--pull-latest-code-from-git) | Download streamlined Docker Compose and Swan AI backend | `EC2 SSH` |
| 7 | [Step 7 — Configure Production Environment (`others/.env`)](#step-7--configure-production-environment-othersenv) | Set cloud credentials using template navigation (no secrets in git) | `EC2 SSH` |
| 8 | [Step 8 — Build and Launch the Backend Container](#step-8--build-and-launch-the-backend-container) | Start single FastAPI container via Docker Compose | `EC2 SSH` |
| 9 | [Step 9 — Run Alembic Database Migrations](#step-9--run-alembic-database-migrations) | Apply schema migrations directly to AWS RDS MySQL | `EC2 SSH` |
| 10 | [Step 10 — Test Internal Backend Health](#step-10--test-internal-backend-health) | Verify FastAPI responds locally on port `8000` | `EC2 SSH` |
| 11 | [Step 11 — Configure Nginx Reverse Proxy with SSE Streaming](#step-11--configure-nginx-reverse-proxy-with-sse-streaming) | Set up port 80 routing, buffering rules, and upload limits | `EC2 SSH` |
| 12 | [Step 12 — Configure Ubuntu Firewall (UFW)](#step-12--configure-ubuntu-firewall-ufw) | Restrict host network exposure to SSH and Nginx only | `EC2 SSH` |
| 13 | [Step 13 — Connect Vercel Frontend to EC2 Backend](#step-13--connect-vercel-frontend-to-ec2-backend) | Configure Vercel API rewrites and environment variables | Vercel / Git |
| 14 | [Step 14 — End-to-End Application Smoke Test](#step-14--end-to-end-application-smoke-test) | Verify authentication, document uploads, and Swan AI chat | Browser |
| 15 | [Step 15 — Server Health & Resource Monitoring](#step-15--server-health--resource-monitoring) | Monitor RAM, CPU, container logs, and swap usage | `EC2 SSH` |

---

## Core Concepts: Nginx & UFW Explained

### 1. What is Nginx, and where does its configuration file live?

> [!NOTE]
> **Do I need to create an Nginx code file in my project Git repository?**  
> **No.** You do **not** create an Nginx file inside your Git repository or VS Code workspace.

* **What Nginx is:** Nginx is a high-performance web server software installed directly on the Ubuntu operating system of your AWS EC2 server (`sudo apt install nginx`).
* **Where the file is created:** On the remote Ubuntu server, Nginx configurations live in `/etc/nginx/sites-available/`.
* **How you create it:** You log in to EC2 via SSH and open the text editor `nano` in your terminal:
  ```bash
  sudo nano /etc/nginx/sites-available/pkb
  ```
  You paste the configuration block directly into that terminal editor, save the file, and create a shortcut (symbolic link) in `/etc/nginx/sites-enabled/`.

#### Why do we need Nginx in front of Docker?
1. **Reverse Proxy (Port 80 $\rightarrow$ Port 8000):** Your Docker container runs FastAPI internally bound to `127.0.0.1:8000`. Public web users access standard port `80` (HTTP) or `443` (HTTPS). Nginx receives external web requests and securely hands them to FastAPI inside Docker.
2. **Swan AI Real-Time Streaming (`proxy_buffering off;`):** Standard web proxies wait to gather the entire server response before sending it to the user. Because Swan AI generates answers word-by-word (Server-Sent Events / SSE), buffering would cause the user to see a freeze for 15 seconds, followed by the entire text dumping at once. `proxy_buffering off;` instructs Nginx to pass each word to the browser immediately as Gemini produces it.
3. **Upload Size Limits (`client_max_body_size 50M;`):** By default, Nginx blocks file uploads larger than 1 MB (`413 Request Entity Too Large`). We configure a 50 MB allowance so documents and PDFs upload smoothly to Swan Drive.
4. **Future HTTPS / SSL:** When you attach a custom domain, Nginx allows you to set up free Let's Encrypt SSL certificates (`certbot --nginx`) in one command.

---

### 2. What is UFW (Uncomplicated Firewall)?

* **What UFW is:** UFW is Ubuntu's built-in Linux firewall. It manages which incoming network packets are allowed into the operating system.
* **Why use UFW when AWS already has Security Groups?**  
  AWS Security Groups act as the outer perimeter fence. UFW acts as the locked front door on the server itself. This provides **Defense-in-Depth**: even if an AWS rule is accidentally set to open all ports, UFW ensures only port 22 (SSH for you) and port 80/443 (HTTP/HTTPS for Nginx) can reach the operating system.

---

### 3. Why `t3.micro` Works Now

In the previous `deploy-1` setup, your EC2 server was running local Docker containers for MySQL 8.0, Redis, and Qdrant. Together, those local databases consumed ~1,200 MB of RAM, forcing the use of `t3.small` (2 GB RAM).

Now that state is moved to cloud providers:
- **Relational Data:** AWS RDS MySQL (0 MB on EC2)
- **Vector DB:** Qdrant Cloud (0 MB on EC2)
- **Cache:** Upstash Redis Serverless (0 MB on EC2)
- **Object Storage:** AWS S3 (0 MB on EC2)

The EC2 instance now runs **only** the FastAPI backend container (~150 MB RAM) alongside Nginx and the Ubuntu OS (~180 MB RAM). Total active RAM is **~330 MB**, which operates comfortably within the 1 GB physical memory of an **AWS Free Tier `t3.micro`** instance.

---

## Terminal Contexts (Kubuntu vs EC2)

Every command in this guide is tagged with where it must be run:

| Label | Environment | Prompt Example |
| :--- | :--- | :--- |
| **`LOCAL KUBUNTU`** | Your local computer running Kubuntu Linux (Bash) | `dell@kubuntu:~/Sun_Development/projects/Personal_Knowledge_Base$` |
| **`EC2 SSH`** | Remote terminal session logged into your AWS EC2 Ubuntu server | `ubuntu@ip-16-192-205-239:~$` |
| **`AWS Console`** | Web browser on your computer logged into aws.amazon.com | AWS Management Console UI |

> [!IMPORTANT]
> In all commands below, replace `<YOUR_EC2_ELASTIC_IP>` with your actual AWS Elastic IP address (e.g. `16.192.205.239`).

---

## Step 1 — Resize Existing EC2 Instance to `t3.micro`

You do **not** need to create a new EC2 instance. You can resize your existing instance in under 2 minutes.

**Run in: `AWS Console`**

1. Navigate to **EC2 $\rightarrow$ Instances**.
2. Select your existing backend instance.
3. Click **Instance state** $\rightarrow$ **Stop instance**.
   - Wait 30–60 seconds until the instance state displays **Stopped** (red circle).
4. Click **Actions** $\rightarrow$ **Instance settings** $\rightarrow$ **Change instance type**.
5. In the dropdown, select **`t3.micro`** (1 vCPU, 1 GiB Memory — Free tier eligible).
6. Click **Apply**.
7. Click **Instance state** $\rightarrow$ **Start instance**.
   - Wait until state displays **Running** and status checks show `2/2 checks passed`.

> [!NOTE]
> Because your instance has an **Elastic IP** associated with it, stopping and starting the instance **preserves your IP address**. Your IP will not change.

---

## Step 2 — Verify AWS RDS Security Group Inbound Rule

Your backend on EC2 needs network permission to reach your AWS RDS MySQL database on port `3306`.

**Run in: `AWS Console`**

1. Go to **RDS $\rightarrow$ Databases $\rightarrow$ Click your MySQL DB instance identifier**.
2. Under the **Connectivity & security** tab, look at **VPC security groups** and click the active security group link.
3. Click the **Inbound rules** tab $\rightarrow$ click **Edit inbound rules**.
4. Verify or add a rule:
   - **Type:** `MySQL/Aurora` (Port `3306`)
   - **Protocol:** `TCP`
   - **Source:** Either your EC2 Security Group ID (e.g. `sg-0xxxxxxxxxxxx`) **OR** your EC2 Elastic IP as a single host CIDR: `<YOUR_EC2_ELASTIC_IP>/32`.
5. Click **Save rules**.

---

## Step 3 — Connect to EC2 from Local Kubuntu

Open your terminal in Kubuntu to connect to your resized instance.

### 3.1 Verify Private Key Permissions

**Run in: `LOCAL KUBUNTU`**

```bash
chmod 400 ~/.ssh/pkb-aws-password.pem
```

* **Purpose:** Sets file permissions so only your user can read the key. SSH rejects `.pem` files that are accessible to other system users.
* **Expected output:** Command completes silently with no error.

### 3.2 SSH into the Server

**Run in: `LOCAL KUBUNTU`**

```bash
ssh -i ~/.ssh/pkb-aws-password.pem ubuntu@<YOUR_EC2_ELASTIC_IP>
```

* **Purpose:** Opens an encrypted remote shell session on your EC2 instance as user `ubuntu`.
* **Expected output:** The terminal prompt changes to:
  ```text
  ubuntu@ip-xxx-xxx-xxx-xxx:~$
  ```

---

## Step 4 — Clean Up Old Docker Containers & Reclaim Disk Space

Your existing EC2 instance previously ran local `mysql:8.0`, `redis`, and `qdrant` containers. Cleaning these up frees several gigabytes of disk space and guarantees zero conflicting ports.

**Run in: `EC2 SSH`**

### 4.1 Stop Old Containers and Remove Old Database Volumes

```bash
cd ~/Personal_Knowledge_Base
docker compose down -v
```

* **What it does:**
  - `down`: Stops and terminates any containers created by previous docker-compose runs.
  - `-v`: Deletes the legacy local Docker named volumes (such as `mysql_data`, `redis_data`, `qdrant_data`), purging old local database files from disk.
* **Expected output:**
  ```text
  [+] Running ...
  ✔ Container ... Removed
  ✔ Volume personal_knowledge_base_mysql_data Removed
  ```

### 4.2 Prune Unused Docker Images and Cache

```bash
docker system prune -a --volumes -f
```

* **What it does:**
  - `-a`: Removes all unattached Docker images (including the heavy `mysql:8.0` ~500 MB and `qdrant/qdrant` ~350 MB images).
  - `--volumes`: Removes dangling volumes.
  - `-f`: Forces removal without requiring manual confirmation.
* **Expected output:** Prints the list of deleted image layers and reports: `Total reclaimed space: 2.xxGB`.

---

## Step 5 — Verify Existing Swap Space on EC2

Because you already configured swap in `deploy-1`, let's verify that the 2 GB swap file is still recognized after switching to `t3.micro`.

**Run in: `EC2 SSH`**

```bash
free -h
```

* **What it does:** Displays total, used, and available physical memory (Mem) and swap space (Swap) in human-readable units (MiB / GiB).
* **Expected output:**
  ```text
                 total        used        free      shared  buff/cache   available
  Mem:           961Mi       140Mi       640Mi       1.0Mi       180Mi       820Mi
  Swap:          2.0Gi          0B       2.0Gi
  ```

> [!NOTE]
> If for any reason `Swap: 0B` is shown (e.g. after a fresh OS install), run:
> ```bash
> sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
> ```

---

## Step 6 — Pull Latest Code from Git

Now update your EC2 repository with the latest codebase, including the cleaned-up Docker Compose setup, slotProps frontend fixes, and multi-format Swan AI RAG pipeline.

**Run in: `EC2 SSH`**

```bash
cd ~/Personal_Knowledge_Base
git status
```

* **Purpose:** Checks that your working directory is clean before pulling.
* **Expected output:** `On branch main`, `nothing to commit, working tree clean`.

```bash
git pull origin main
```

* **Purpose:** Fetches and merges the latest commits from GitHub into your server repository.
* **Expected output:** Lists updated files, including `docker-compose.yml`, `backend/`, and frontend components.

---

## Step 7 — Configure Production Environment (`others/.env`)

The backend container receives its environment configuration from the server's private file `others/.env`.

> [!IMPORTANT]
> The repository does **not** track `.env` files in Git to protect your secrets.  
> Refer to the template file [`others/.env.example`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/others/.env.example) to see all variable names and descriptions.

**Run in: `EC2 SSH`**

### 7.1 Inspect or Create `others/.env`

If you already created `others/.env` in `deploy-1`, open it:

```bash
nano ~/Personal_Knowledge_Base/others/.env
```

*(If creating for the first time, copy the template first: `cp others/.env.example others/.env`)*.

### 7.2 Verify Required Settings

Inside `nano`, ensure your actual cloud connection credentials are set:

1. **Security & Server:**
   - `SECRET_KEY`: Your generated JWT secret key.
   - `VITE_API_URL`: `/` (or `http://<YOUR_EC2_ELASTIC_IP>`).
2. **Database:**
   - `DATABASE_URL`: `mysql+pymysql://<DB_USER>:<DB_PASSWORD>@<YOUR-RDS-ENDPOINT>:3306/personal_knowledge_base`
3. **CORS:**
   - `CORS_ORIGINS`: `["http://localhost:5173", "https://personal-knowledge-base-blue.vercel.app"]`
4. **AWS S3:**
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_ENDPOINT_URL`, `S3_BUCKET_NAME`
5. **Gemini AI:**
   - `GEMINI_API_KEY`, `GEMINI_EMBEDDING_MODEL=gemini-embedding-2`
6. **Qdrant Cloud:**
   - `QDRANT_HOST=https://<cluster-id>.<region>.aws.cloud.qdrant.io`
   - `QDRANT_API_KEY=your_qdrant_cloud_api_key`
7. **Upstash Redis:**
   - `UPSTASH_REDIS_REST_URL=https://<name>.upstash.io`
   - `UPSTASH_REDIS_REST_TOKEN=your_token`

*Save and exit nano:* Press `Ctrl + O`, then `Enter`, then `Ctrl + X`.

---

## Step 8 — Build and Launch the Backend Container

Inspect [`docker-compose.yml`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/docker-compose.yml). Notice that it now defines **only** the `backend` service with `env_file: ./others/.env`. It contains zero hardcoded values, zero secrets, and zero local database containers.

**Run in: `EC2 SSH`**

### 8.1 Build the Image and Start the Container

```bash
cd ~/Personal_Knowledge_Base
docker compose --env-file ./others/.env up -d --build
```

* **What each flag does:**
  - `--env-file ./others/.env`: Tells Docker Compose where to read the environment variables.
  - `up`: Builds, creates, and starts the container.
  - `-d`: Detached mode (runs the container in the background).
  - `--build`: Forces Docker to build a fresh image from `./backend/Dockerfile`.
* **Expected output:**
  ```text
  [+] Building ...
  [+] Running 2/2
  ✔ Network personal_knowledge_base_default  Created
  ✔ Container pkb-backend                   Started
  ```

### 8.2 Check Container Status

```bash
docker compose ps
```

* **Purpose:** Confirms the container is running and healthy.
* **Expected output:**
  ```text
  NAME          IMAGE                             COMMAND                  SERVICE   STATUS         PORTS
  pkb-backend   personal_knowledge_base-backend   "gunicorn -k uvicorn…"   backend   Up 15 seconds  127.0.0.1:8000->8000/tcp
  ```
  *(Notice port `8000` is bound strictly to `127.0.0.1`, which protects it from direct public exposure and requires traffic to go through Nginx).*

### 8.3 Check Application Startup Logs

```bash
docker compose logs --tail=40 backend
```

* **Purpose:** Checks the Gunicorn/Uvicorn server startup output.
* **Expected output:**
  ```text
  [INFO] Starting gunicorn ...
  [INFO] Listening at: http://0.0.0.0:8000
  [INFO] Using worker: uvicorn.workers.UvicornWorker
  [INFO] Booting worker with pid: ...
  [INFO] Application startup complete.
  ```

---

## Step 9 — Run Alembic Database Migrations

Now execute the database migrations inside the running container to update your AWS RDS MySQL schema to the latest version.

**Run in: `EC2 SSH`**

```bash
docker compose --env-file ./others/.env exec backend alembic upgrade head
```

* **What it does:**
  - `exec backend`: Executes a command inside the running `pkb-backend` container.
  - `alembic upgrade head`: Reads your migration history in `backend/alembic/versions/` and applies any pending table creations or column updates to AWS RDS.
* **Expected output:**
  ```text
  INFO  [alembic.runtime.migration] Context impl MySQLImpl.
  INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
  INFO  [alembic.runtime.migration] Running upgrade -> xxxxx, ...
  ```

---

## Step 10 — Test Internal Backend Health

Verify that the FastAPI application is responding over localhost on the EC2 server before configuring Nginx.

**Run in: `EC2 SSH`**

```bash
curl -s http://127.0.0.1:8000/system/ping
```

* **What it does:** Sends an HTTP GET request to FastAPI's ping route on port 8000.
* **Expected output:**
  ```json
  {"status":"ok","message":"pong"}
  ```

If you receive this JSON response, the backend application and its connection to AWS RDS MySQL are fully operational.

---

## Step 11 — Configure Nginx Reverse Proxy with SSE Streaming

Now we configure Nginx on the host operating system to accept external HTTP requests on port 80 and route them to `127.0.0.1:8000`.

### 11.1 Install Nginx

**Run in: `EC2 SSH`**

```bash
sudo apt update && sudo apt install -y nginx
```

* **Purpose:** Installs the official Nginx package on Ubuntu.
* **Expected output:** Nginx installs and starts automatically.

### 11.2 Create the Configuration File

**Run in: `EC2 SSH`**

Open a new configuration file in `nano`:

```bash
sudo nano /etc/nginx/sites-available/pkb
```

Paste the following block into the editor:

```nginx
server {
    listen 80;
    server_name _;

    # Maximum allowed request body (allows up to 50 MB document uploads)
    client_max_body_size 50M;

    # Compression for text and JSON responses
    gzip on;
    gzip_types application/json text/plain text/css application/javascript;
    gzip_min_length 1000;

    location / {
        # Forward traffic to internal FastAPI container
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # Standard client identity headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # CRITICAL for Swan AI RAG Streaming:
        # Prevents Nginx from holding tokens in memory before sending.
        # Tokens are delivered to the browser in real-time as Gemini produces them.
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_set_header Connection '';
        chunked_transfer_encoding on;
    }
}
```

*To save and exit `nano`:*
1. Press `Ctrl + O`
2. Press `Enter` (to confirm filename `/etc/nginx/sites-available/pkb`)
3. Press `Ctrl + X`

### 11.3 Explanation of Every Directive in this Nginx File

| Directive | What It Does & Why It Is Essential |
| :--- | :--- |
| `listen 80;` | Instructs Nginx to listen for standard unencrypted HTTP web traffic on port 80. |
| `server_name _;` | Acts as a wildcard/catch-all for any incoming hostname or IP address. |
| `client_max_body_size 50M;` | Allows document uploads up to 50 MB. Without this, uploading a 5 MB PDF causes Nginx to reject the request with `413 Request Entity Too Large`. |
| `proxy_pass http://127.0.0.1:8000;` | Relays incoming requests to the internal Docker container running on port 8000. |
| `proxy_buffering off;` | **Swan AI Streaming:** Prevents Nginx from buffering Server-Sent Events (SSE). Streams tokens word-by-word to the browser. |
| `proxy_read_timeout 300s;` | Extends timeout to 5 minutes so long document indexing or complex RAG queries do not trigger `504 Gateway Timeout`. |
| `proxy_set_header X-Forwarded-For` | Forwards the user's real public IP address to FastAPI for audit logs and security checks. |

### 11.4 Activate Configuration and Reload Nginx

**Run in: `EC2 SSH`**

1. Remove the default Apache/Nginx placeholder site:
   ```bash
   sudo rm -f /etc/nginx/sites-enabled/default
   ```
   * *Purpose:* Removes the generic "Welcome to Nginx" page so it does not conflict with our app.

2. Create a symbolic link to activate `pkb`:
   ```bash
   sudo ln -s /etc/nginx/sites-available/pkb /etc/nginx/sites-enabled/pkb
   ```
   * *Purpose:* Nginx reads active sites from `sites-enabled/`. This link activates your configuration without duplicating files.

3. Test configuration syntax:
   ```bash
   sudo nginx -t
   ```
   * *Purpose:* Validates configuration files for syntax errors before reloading.
   * *Expected output:*
     ```text
     nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
     nginx: configuration file /etc/nginx/nginx.conf test is successful
     ```

4. Reload Nginx to apply changes:
   ```bash
   sudo systemctl restart nginx
   ```
   * *Purpose:* Restarts the Nginx system service with the new settings.

### 11.5 Test Nginx from Local Kubuntu

Now test that Nginx is answering on port 80 from outside the server.

**Run in: `LOCAL KUBUNTU`**

```bash
curl -s http://<YOUR_EC2_ELASTIC_IP>/system/ping
```

* **Purpose:** Queries the public Elastic IP over port 80.
* **Expected output:**
  ```json
  {"status":"ok","message":"pong"}
  ```

---

## Step 12 — Configure Ubuntu Firewall (UFW)

Protect your EC2 server using Ubuntu's built-in firewall.

**Run in: `EC2 SSH`**

### 12.1 Set Default Traffic Policies

```bash
sudo ufw default deny incoming
```
* **Purpose:** Blocks all inbound connection attempts unless an explicit rule allows them.

```bash
sudo ufw default allow outgoing
```
* **Purpose:** Allows the server to make outbound connections to download packages, call Gemini API, and connect to RDS, Qdrant, Upstash, and S3.

### 12.2 Allow SSH and Web Traffic

```bash
sudo ufw allow OpenSSH
```
* **Purpose:** Opens port `22` for SSH.  
  *(CRITICAL: Running this before enabling UFW ensures you do not get locked out of your server!)*

```bash
sudo ufw allow 'Nginx Full'
```
* **Purpose:** Opens port `80` (HTTP) and port `443` (HTTPS) for public web traffic.

### 12.3 Enable the Firewall

```bash
sudo ufw --force enable
```
* **Purpose:** Activates the firewall rules immediately and persists them across server reboots.

### 12.4 Verify Active Rules

```bash
sudo ufw status verbose
```

* **Expected output:**
  ```text
  Status: active
  Logging: on (low)
  Default: deny (incoming), allow (outgoing), disabled (routed)
  New profiles: skip

  To                         Action      From
  --                         ------      ----
  22/tcp (OpenSSH)           ALLOW IN    Anywhere
  80,443/tcp (Nginx Full)    ALLOW IN    Anywhere
  22/tcp (OpenSSH (v6))      ALLOW IN    Anywhere (v6)
  80,443/tcp (Nginx Full (v6)) ALLOW IN Anywhere (v6)
  ```

---

## Step 13 — Connect Vercel Frontend to EC2 Backend

Because your frontend is hosted on Vercel (`https://personal-knowledge-base-blue.vercel.app`), browser security prevents the HTTPS frontend from making direct HTTP calls to your EC2 IP (Mixed Content restriction).

We solve this using **Vercel Server-Side Rewrites**.

### 13.1 Verify Vercel Rewrites Configuration

Inspect [`frontend/vercel.json`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/frontend/vercel.json):

```json
{
  "rewrites": [
    {
      "source": "/backend/:path*",
      "destination": "http://<YOUR_EC2_ELASTIC_IP>/:path*"
    }
  ]
}
```

* **How it works:** When your React application makes a call to `/backend/auth/login`, Vercel's server receives the call over HTTPS, proxies it behind the scenes to `http://<YOUR_EC2_ELASTIC_IP>/auth/login`, and returns the response over HTTPS. The user's browser never encounters a mixed-content block.

### 13.2 Update `destination` with your Elastic IP

On your local Kubuntu machine, edit [`frontend/vercel.json`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/frontend/vercel.json):
- Replace the destination IP placeholder with your actual `<YOUR_EC2_ELASTIC_IP>`.

Commit and push to GitHub:

**Run in: `LOCAL KUBUNTU`**

```bash
git add frontend/vercel.json
git commit -m "chore: point vercel backend rewrite to ec2 elastic ip"
git push origin main
```

### 13.3 Set Vercel Environment Variables

1. Open your project on **Vercel Dashboard** $\rightarrow$ **Settings** $\rightarrow$ **Environment Variables**.
2. Set or update:
   - `VITE_API_URL` = `/backend`
3. Click **Save**.
4. Go to **Deployments** $\rightarrow$ Click the latest deployment $\rightarrow$ Click **Redeploy** to apply the updated environment variable.

---

## Step 14 — End-to-End Application Smoke Test

Test the entire application stack in your web browser:

1. **Access Web App:**
   - Open your Vercel URL in your browser: `https://personal-knowledge-base-blue.vercel.app`
   - Verify the brand header displays **Swan Drive** and the custom swan SVG logo.
2. **User Registration / Login:**
   - Create a test account or log in with existing credentials.
   - Verifies: Vercel frontend $\rightarrow$ Nginx $\rightarrow$ FastAPI $\rightarrow$ AWS RDS MySQL authentication query.
3. **Document Upload (My Drive):**
   - Click upload and select a PDF or Markdown document (e.g. `sample.pdf`).
   - Verifies: AWS S3 presigned URL generation, document extraction worker, and Qdrant Cloud vector indexing.
4. **Swan AI RAG Chat Query:**
   - Open the **Swan AI** tab.
   - Ask a question specific to your uploaded document.
   - Verifies: Upstash Redis cache check $\rightarrow$ Gemini embedding $\rightarrow$ Qdrant Cloud similarity search $\rightarrow$ Gemini generation with real-time token streaming and citations.

---

## Step 15 — Server Health & Resource Monitoring

Verify that resource consumption on the `t3.micro` instance remains low and healthy.

**Run in: `EC2 SSH`**

### 15.1 Check Live Container Resource Usage

```bash
docker stats --no-stream
```

* **Purpose:** Inspects CPU, memory usage, and memory percentage of running containers.
* **Expected output:**
  ```text
  CONTAINER ID   NAME          CPU %     MEM USAGE / LIMIT     MEM %     NET I/O
  xxxxxxxxxxxx   pkb-backend   0.20%     145.2MiB / 961.4MiB   15.10%    ...
  ```
  *(Memory usage is ~145 MB, leaving over 800 MB of physical RAM available).*

### 15.2 Check Host RAM and Swap

```bash
free -h
```

* **Expected output:** `available` memory is consistently above `600Mi`, and `Swap` used is `0B` or minimal.

### 15.3 Check Real-Time Logs

```bash
docker compose logs -f --tail=30 backend
```

*(Press `Ctrl + C` to stop following logs).*

---

## Completion Checklist

- [ ] Existing EC2 instance stopped, resized to `t3.micro`, and restarted in AWS Console.
- [ ] AWS RDS Security Group permits inbound port `3306` from `<YOUR_EC2_ELASTIC_IP>/32`.
- [ ] SSH connection successful from Kubuntu with `chmod 400 ~/.ssh/pkb-aws-password.pem`.
- [ ] Old local database containers (`mysql`, `redis`, `qdrant`) and volumes removed with `docker compose down -v` and `docker system prune -a --volumes -f`.
- [ ] 2 GB Swap space confirmed active with `free -h`.
- [ ] Latest code pulled on EC2 via `git pull origin main`.
- [ ] Private credentials verified in server's `others/.env` using [`others/.env.example`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/others/.env.example).
- [ ] Single backend container launched with `docker compose --env-file ./others/.env up -d --build`.
- [ ] Database migrations applied with `alembic upgrade head`.
- [ ] Nginx configured at `/etc/nginx/sites-available/pkb` with `proxy_buffering off;` and enabled.
- [ ] UFW firewall enabled allowing only `OpenSSH` (port 22) and `Nginx Full` (port 80/443).
- [ ] Vercel frontend rewrite in [`frontend/vercel.json`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/frontend/vercel.json) points to `<YOUR_EC2_ELASTIC_IP>`.
- [ ] End-to-end smoke test passed (Login, My Drive upload, Swan AI streaming query).
