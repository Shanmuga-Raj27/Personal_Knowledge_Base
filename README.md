# Personal Knowledge Base (PKB)

## 📌 Project Overview
The **Personal Knowledge Base** is a web-based cloud document workspace designed to store files directly in cloud storage and search them faster. Currently, this is an educational project built to learn and teach core software engineering and cloud concepts, including:
* Cloud S3 storage integration
* Secure user authentication with JSON Web Tokens (JWT)
* Scalable backend architecture
* Relational database design
* AI integrations (embeddings and language models)

### 💡 The Problem It Solves
* **Traditional Approach**: Traditional file managers store files in a rigid folder-based structure. When you search for a file, you are limited to searching only by its exact filename.
* **The Solution**: The Personal Knowledge Base stores files directly in cloud storage and attaches custom metadata (titles, descriptions, and tags) to each file. Rather than relying solely on file names, the system uses AI-powered semantic search. This allows you to search files based on relevant patterns, meaning, and metadata context, making file retrieval much faster and more efficient. It also lays the foundation for future Retrieval-Augmented Generation (RAG) applications to explain concepts across multiple large documents.


---

## 🗺️ Project Roadmap
The project is structured around three major versions:

| Version | Status | Core Scope | Core Technical Focus |
| :--- | :--- | :--- | :--- |
| **V1** | **Completed** | Secure User Auth, Direct-to-S3 Uploads, Metadata CRUD, AI Summarization | JWT auth, S3/B2 presigned URLs, MySQL metadata, Pytest coverage |
| **V2** | **In Development** | AI-powered file semantic search | Google GenAI SDK (`gemini-embedding-2`), Qdrant Vector DB |
| **V3** | **In Development** | Advanced Retrieval-Augmented Generation (RAG) | Document chunking, multi-source retrieval, grounded conversational query interface |

---

## 🛠️ Technology Stack
The application is built using a modern, decoupled stack:

### Backend
* **Language & Framework**: Python 3.12+ & FastAPI (Asynchronous framework)
* **Database & ORM**: MySQL 8.0 & SQLAlchemy 2.0 (PyMySQL adapter)
* **Migrations**: Alembic 1.19.1
* **Authentication**: JWT (HS256) via `python-jose` & Password hashing via Argon2id (`passlib[argon2]`)
* **Validation & Settings**: Pydantic v2 & Pydantic Settings
* **Testing**: Pytest with mock integrations (`pytest-asyncio`, `httpx`)
* **Server**: Uvicorn

### Frontend
* **Core Library**: React (v19) & Vite
* **UI Components**: Material UI (MUI) & Emotion CSS
* **HTTP Client**: Axios with automatic JWT Authorization interceptors

### Object Storage Configuration
* **Development & Testing**: [Backblaze B2 Object Storage](https://www.backblaze.com/cloud-storage) (S3-compatible API) for cost-efficiency.
* **Production Deployment**: [AWS S3](https://aws.amazon.com/s3/) for storage and [AWS EC2](https://aws.amazon.com/ec2/) for application hosting.

---

## 📂 Repository Directory Structure

```
Personal_Knowledge_Base/
├── .agents/                        # Agentic configs and skills
├── backend/                        # Backend FastAPI Application
│   ├── alembic/                    # Database migrations environment
│   │   ├── versions/               # Migration scripts
│   │   ├── env.py                  # Alembic environment configuration
│   │   ├── README                  # Alembic README
│   │   └── script.py.mako          # Alembic template
│   ├── app/                        # FastAPI application core
│   │   ├── apis/                   # API Routers
│   │   │   └── routes/             # Endpoints
│   │   │       ├── auth.py         # Authentication endpoints
│   │   │       ├── system.py       # System health/monitoring
│   │   │       └── upload_file.py  # File upload flow endpoints
│   │   ├── auth/                   # Authentication helper functions
│   │   │   └── auth.py             # User retrieval and JWT checks
│   │   ├── core/                   # System core configurations
│   │   │   ├── config.py           # Configuration loading via Pydantic
│   │   │   └── security.py         # Password hashing & JWT tokens
│   │   ├── database/               # Database management
│   │   │   ├── database.py         # DB connection & Session factory
│   │   │   └── db_models.py        # SQLAlchemy database models
│   │   ├── schemas/                # Pydantic validation schemas
│   │   │   ├── file.py             # File-related API schemas
│   │   │   └── schemas.py          # User & Authentication schemas
│   │   ├── scripts/                # Development helper scripts
│   │   │   └── set_cors_secure.py  # Script for setting CORS
│   │   ├── services/               # Internal and external services
│   │   │   ├── AI/                 # AI service models/stubs
│   │   │   └── AWS/                # AWS integrations
│   │   │       └── s3_service.py   # Direct S3/B2 file upload handler
│   │   └── utils/                  # Core utility files (placeholders)
│   ├── tests/                      # Pytest suite
│   │   ├── integration/            # Integration tests
│   │   │   └── routes/             # Route integration tests
│   │   │       ├── test_system.py
│   │   │       └── test_upload_file.py
│   │   ├── unit/                   # Unit tests
│   │   │   └── services/           # Service unit tests
│   │   │       └── test_s3_service.py
│   │   └── test_auth_and_files.py  # Multi-tenant scoping and JWT tests
│   ├── alembic.ini                 # Alembic configuration
│   ├── main.py                     # API app factory
│   ├── pyproject.toml              # Project dependencies configuration
│   └── requirements.txt            # Python requirements file
├── documentation/                  # Project roadmap and specs
│   ├── project_plan/               # Phased project planning
│   │   ├── plan_phase-3.md
│   │   ├── plan_phase-4.md
│   │   ├── plan_phase-6.1.md
│   │   ├── plan_phase-6.md
│   │   └── project_plan_v1.md      # V2 AI semantic search implementation plan
│   └── technical_documentation/    # Phase-wise technical documentations
│       ├── phase-1.md              # Technical documentation (Phase 1 core architecture)
│       ├── phase-2.md
│       ├── phase-3.md
│       ├── phase-4.md
│       ├── phase-5.md
│       └── phase-6.md              # Authentication & Multi-user ownership specs
├── frontend/                       # React Frontend Application
│   ├── public/                     # Static assets
│   ├── src/                        # Source files
│   │   ├── apis/                   # Backend API integrations
│   │   │   ├── authApi.js          # Authentication API functions
│   │   │   ├── axiosClient.js      # Axios client configuration with JWT interceptors
│   │   │   ├── documentApi.js      # Files & documents API functions
│   │   │   └── systemApi.js        # System monitoring API functions
│   │   ├── assets/                 # Local assets (images, icons)
│   │   ├── components/             # Reusable UI components
│   │   │   ├── DeleteConfirmDialog.jsx
│   │   │   ├── EditMetadataDialog.jsx
│   │   │   ├── FileList.jsx
│   │   │   ├── FileRow.jsx
│   │   │   ├── Header.jsx
│   │   │   └── SearchHeader.jsx
│   │   ├── pages/                  # Page layouts
│   │   │   └── AuthPage.jsx        # Login / Registration view
│   │   ├── services/               # Frontend business services
│   │   │   └── authService.js      # Local authentication service
│   │   ├── App.css                 # Main application CSS
│   │   ├── App.jsx                 # Layout and main view orchestrator
│   │   ├── index.css               # Global CSS styles
│   │   └── main.jsx                # Application root entry point
│   ├── eslint.config.js            # Linter configuration
│   ├── index.html                  # Core HTML file
│   ├── package.json                # NPM configuration
│   └── vite.config.js              # Vite bundler configuration
├── others/                         # Secrets and environment files
│   ├── .env                        # Local environment secrets (ignored in Git)
│   └── .python-version             # Python local environment version
├── prompt-base/                    # Prompt snippets & guidelines
│   └── tech-doc.txt
├── .gitignore                      # Git ignored files list
└── README.md                       # Repository entry point document (this file)
```

---
