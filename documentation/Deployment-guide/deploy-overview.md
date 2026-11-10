# Swan Drive — Deployment Architecture & Evolution Overview

> **Application:** Swan Drive (Personal Knowledge Base)  
> **Audience:** Developers, Architects, and Technical Reviewers  
> **Purpose:** High-level architectural roadmap, system evolution, component responsibilities, and request flows.  
> **Implementation Guides:** See [`deploy-1.2.md`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/documentation/Deployment-guide/deploy-1.2.md) for server deployment and [`CI-CD.md`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/documentation/Deployment-guide/CI-CD.md) for GitHub Actions automation.

---

## 1. Documentation Suite Navigation

This repository organizes deployment into distinct, focused documents. Commands, configurations, and scripts are maintained in their respective guides to avoid duplication:

| Document | Purpose | Status |
| :--- | :--- | :--- |
| **[`deploy-overview.md`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/documentation/Deployment-guide/deploy-overview.md)** | **This Document:** Architecture blueprint, cloud-native evolution, and data flows. | **Active (Current)** |
| **[`deploy-1.2.md`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/documentation/Deployment-guide/deploy-1.2.md)** | Step-by-step deployment to AWS EC2 `t3.micro` Free Tier connected to cloud services. | **Active (Current)** |
| **[`CI-CD.md`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/documentation/Deployment-guide/CI-CD.md)** | Step-by-step CI/CD automation guide with manual release button (`workflow_dispatch`). | **Active (Current)** |
| **[`deploy-1.1.md`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/documentation/Deployment-guide/deploy-1.1.md)** | Legacy Phase 1 guide (All-in-one local Docker containers on `t3.small`). | *Archived Reference* |
| **[`deploy-2.md`](file:///home/dell/Sun_Development/projects/Personal_Knowledge_Base/documentation/Deployment-guide/deploy-2.md)** | Legacy Phase 2 reference (Custom domains, SSL, database backup scripts). | *Archived Reference* |

---

## 2. The Architecture Evolution: Why We Switched

### 2.1 The Legacy Monolithic Setup (`deploy-1.1.md`)
In the initial MVP deployment, the entire application stack was bundled inside a single AWS EC2 virtual machine:

```text
               ┌────────────────────────────────────────────────────────┐
               │                LEGACY AWS EC2 INSTANCE                 │
               │                                                        │
               │   Nginx (Port 80)                                      │
               │   ├── Serves React Build Files (/var/www/pkb)          │
               │   └── Reverse Proxies API requests to :8000            │
               │                                                        │
               │   Docker Compose Engine                                │
               │   ├── backend (FastAPI + Gunicorn)         ~150 MB RAM │
               │   ├── mysql:8.0 (Local database container) ~500 MB RAM │
               │   ├── qdrant (Local vector database)       ~350 MB RAM │
               │   └── redis:7-alpine (Local cache)          ~40 MB RAM │
               │                                                        │
               │   Host Operating System & Nginx            ~200 MB RAM │
               │                                                        │
               │   TOTAL ACTIVE MEMORY: ~1,240 MB – 1,500 MB RAM       │
               │   INSTANCE REQUIRED:   t3.small (Paid / Above Free)    │
               └────────────────────────────────────────────────────────┘
```

### 2.2 Why the Old Architecture Failed in Production
1. **Memory Exhaustion (OOM Kills):**  
   Running MySQL 8, Qdrant, and Redis inside local Docker containers on the same virtual machine consumed ~1.3 GB to 1.5 GB of RAM. This exceeded the 1 GB physical memory of the AWS Free Tier (`t3.micro`), forcing the use of `t3.small` and risking kernel Out-Of-Memory process termination during document indexing.
2. **Disk Storage Creep:**  
   Local MySQL tables, vector embeddings on disk, and Docker image layers rapidly filled the 20 GB root EBS volume.
3. **Complex Future Migrations & Single Point of Failure:**  
   If the EC2 virtual machine crashed, corrupted its disk, or needed a system upgrade, the database, vector index, cache, and API all failed simultaneously. Migrating data to high-availability clusters would require risky, manual database dump and restore procedures.

---

### 2.3 The Modern Cloud-Native Architecture (`deploy-1.2.md`)
We decoupled state, storage, and persistence from the EC2 server, transitioning to specialized, managed cloud services that offer generous Free Tiers:

```text
                        CLIENTS / WEB BROWSERS
                                  │
                                  ▼
               ┌─────────────────────────────────────┐
               │         VERCEL (Edge CDN)           │
               │   • React 19 SPA Frontend           │
               │   • Global CDN Distribution         │
               │   • Serverless API Proxy Rewrite    │
               └──────────────────┬──────────────────┘
                                  │ HTTPS API Requests (/backend/:path*)
                                  ▼
               ┌─────────────────────────────────────┐
               │    AWS EC2 (Ubuntu t3.micro Host)   │
               │                                     │
               │   Nginx Reverse Proxy (:80)         │
               │   • SSE Unbuffered Streaming        │
               │   • 50 MB Upload Allowance          │
               │                  │                  │
               │                  ▼                  │
               │   Docker: pkb-backend (:8000)       │
               │   • FastAPI + Gunicorn (2 Workers)  │
               │   • Modular RAG Document Extractors │
               │   • Active RAM: ~150 MB             │
               │                                     │
               │   TOTAL HOST RAM USAGE: ~330 MB     │
               │   COMFORTABLY FITS AWS FREE TIER    │
               └──────────────────┬──────────────────┘
                                  │
      ┌───────────────────────────┼───────────────────────────┐
      │                           │                           │
      ▼                           ▼                           ▼
┌──────────────┐           ┌──────────────┐           ┌──────────────┐
│AWS RDS MySQL │           │ Qdrant Cloud │           │Upstash Redis │
│(Relational)  │           │ (Vector DB)  │           │(Serverless)  │
│• Users/Auth  │           │• 768-dim RAG │           │• Answer Cache│
│• Doc Metadata│           │  Embeddings  │           │• Rate Limits │
│• Free Tier   │           │• Serverless  │           │• Free Tier   │
└──────────────┘           └──────────────┘           └──────────────┘
      │                           │
      ▼                           ▼
┌──────────────┐           ┌──────────────┐
│    AWS S3    │           │Google Gemini │
│• Raw PDFs    │           │• Embedding-2 │
│• Presigned   │           │• Multi-Model │
│  Upload URLs │           │  Routing API │
└──────────────┘           └──────────────┘
```

---

## 3. Resource & Cost Profile Comparison

By offloading persistence to managed cloud tiers, the EC2 instance transitioned from a heavy database server to a lightweight, stateless compute runner:

| Metric | Old Setup (`deploy-1.1.md`) | Modern Cloud-Native Setup (`deploy-1.2.md`) |
| :--- | :--- | :--- |
| **Relational Database** | Local Docker MySQL (~500 MB RAM) | **AWS RDS MySQL Free Tier** (0 MB on EC2) |
| **Vector Database** | Local Docker Qdrant (~350 MB RAM) | **Qdrant Cloud Free Cluster** (0 MB on EC2) |
| **Caching Layer** | Local Docker Redis (~40 MB RAM) | **Upstash Redis Serverless** (0 MB on EC2) |
| **Frontend Hosting** | Host Nginx directory (~50 MB RAM) | **Vercel Edge Global CDN** (0 MB on EC2) |
| **Backend Compute** | Docker FastAPI container (~150 MB RAM) | **Docker FastAPI container (~150 MB RAM)** |
| **Host System & Nginx** | Ubuntu OS (~180 MB RAM) | **Ubuntu OS + Nginx (~180 MB RAM)** |
| **Total Active RAM** | **~1,250 MB – 1,500 MB** | **~330 MB – 450 MB** |
| **AWS Instance Type** | `t3.small` (Paid tier required) | **`t3.micro` (100% AWS Free Tier Eligible)** |
| **Data Safety & Backups**| Risk of total loss on disk failure | **Automated RDS snapshots & Cloud backups** |

---

## 4. Component Responsibilities

### 4.1 Frontend Layer (Vercel)
- **Technology:** React 19, Vite, Material UI (MUI).
- **Branding:** Swan Drive application suite with Swan AI RAG interface.
- **Hosting:** Vercel Global Edge Network with continuous automatic deployment on git push to `main`.
- **API Routing:** `frontend/vercel.json` rewrites `/backend/:path*` to `http://<YOUR_EC2_ELASTIC_IP>/:path*`. This prevents browser mixed-content restrictions (HTTPS frontend calling HTTP backend).

### 4.2 Compute & Reverse Proxy Layer (AWS EC2 `t3.micro`)
- **Nginx (Host Reverse Proxy):**
  - Listens on public port 80.
  - Passes incoming traffic to the internal container at `127.0.0.1:8000`.
  - Disables proxy buffering (`proxy_buffering off;`) to support Server-Sent Events (SSE) token streaming for Swan AI.
  - Sets upload limit to 50 MB (`client_max_body_size 50M;`).
- **Backend Container (`pkb-backend`):**
  - Python 3.12, FastAPI, Gunicorn with 2 Uvicorn async workers.
  - Stateless execution: reads environment settings exclusively from `others/.env`.
  - Runs Alembic database schema migrations on AWS RDS MySQL.
  - Multi-format ingestion engine extracting text from PDF, Markdown, and TXT files.

### 4.3 Cloud Persistence & Intelligence Layer
- **AWS RDS MySQL:** Authoritative relational store for user identities, password hashes (Argon2id), document metadata, and file access records.
- **Qdrant Cloud:** High-performance vector database hosting collection `document_chunks_v1` with 768-dimensional vector embeddings and Cosine distance metric.
- **Upstash Redis:** Cloud-native serverless Redis accessed via HTTPS REST protocol. Caches RAG query responses (TTL: 3600 seconds) to avoid duplicate AI generation costs.
- **AWS S3 (Secure Storage):** Stores raw user documents. The backend generates short-lived presigned URLs for client downloads, offloading bandwidth from the EC2 server.
- **Google Gemini API:** Generates document embeddings (`gemini-embedding-2`) and performs streaming multi-model RAG generation (`gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-2.5-flash-lite`, `gemini-3-flash`).

---

## 5. End-to-End System Lifecycles

### 5.1 Document Upload & Multi-Format RAG Indexing Flow

```text
User Browser              Vercel / Backend                  AWS S3 & Cloud Services
    │                            │                                     │
    ├─► 1. Request Upload ──────►│                                     │
    │   (file metadata)          ├─► 2. Generate Presigned URL ───────►│ (AWS S3)
    │                            │◄─── Returns upload URL & key ───────┤
    │◄── 3. Receives Presigned ──┤                                     │
    │
    ├─► 4. Direct Upload (PUT) ───────────────────────────────────────►│ (AWS S3 Bucket)
    │                                                                  │
    ├─► 5. Notify Upload Done ──►│                                     │
    │   (triggers worker)        ├─► 6. Save metadata ────────────────►│ (AWS RDS MySQL)
    │                            ├─► 7. Download file bytes ──────────►│ (AWS S3)
    │                            ├─► 8. Extract & chunk text           │
    │                            ├─► 9. Generate Embeddings ──────────►│ (Google Gemini API)
    │                            ├─► 10. Store 768-d vectors ─────────►│ (Qdrant Cloud)
    │◄── 11. Status: Ready ──────┤
```

### 5.2 Swan AI Streaming Query & Retrieval Flow

```text
User Browser              Nginx / FastAPI               Cache / Vector DB / AI
    │                            │                                     │
    ├─► 1. Ask Question (SSE) ──►│                                     │
    │   (POST /rag/query)        ├─► 2. Check Answer Cache ───────────►│ (Upstash Redis)
    │                            │   [If Cache Hit: Return cached text instantly]
    │                            │
    │                            ├─► 3. Embed Query (768-dim) ────────►│ (Google Gemini API)
    │                            ├─► 4. Vector Similarity Search ─────►│ (Qdrant Cloud)
    │                            │◄─── Returns top-K chunk contexts ──┤
    │                            │
    │                            ├─► 5. Stream Generation Request ────►│ (Google Gemini API)
    │                            │◄─── Token stream (word by word) ────┤
    │◄── 6. Real-time SSE ───────┤
    │    Token Streaming         ├─► 7. Cache final answer ───────────►│ (Upstash Redis)
```

---

## 6. Deployment & Automation Strategy

Our deployment process is split into two complementary tracks:

```text
┌────────────────────────────────────────────────────────┐
│  TRACK A: Day-to-Day Infrastructure Execution          │
│  Guide: documentation/Deployment-guide/deploy-1.2.md   │
│                                                        │
│  • Manages EC2 instance sizing (t3.micro).             │
│  • Manages Nginx reverse proxy & UFW firewall on host. │
│  • Connects Vercel rewrites to EC2 Elastic IP.         │
│  • Validates live smoke test in browser.               │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│  TRACK B: Continuous Integration & Deployment (CI/CD)  │
│  Guide: documentation/Deployment-guide/CI-CD.md        │
│                                                        │
│  • CI (Automated): Runs tests & builds in GitHub cloud │
│    on every push without contacting EC2.               │
│  • CD (Manual Button): One-click `workflow_dispatch`   │
│    releases code to EC2 via agentless SSH when the     │
│    server is started by the developer.                 │
└────────────────────────────────────────────────────────┘
```

---

## 7. Architecture Summary & Guiding Principles

1. **Stateless Compute:** The EC2 backend server stores zero persistent application data. If the server is destroyed or resized, zero document or user data is lost.
2. **Cost-First Architecture:** Operates 100% within AWS Free Tier (`t3.micro`), Qdrant Cloud Free Tier, Upstash Redis Free Tier, and Vercel Hobby Tier.
3. **Defense-in-Depth Security:** Protected at three layers:
   - AWS Security Groups (outer network perimeter).
   - Ubuntu UFW Firewall (host port enforcement).
   - Docker private localhost binding (`127.0.0.1:8000`), forcing all traffic through Nginx.
4. **Real-Time Responsiveness:** Unbuffered Nginx reverse proxy ensures Swan AI generates fluid, token-by-token streaming responses for users.
