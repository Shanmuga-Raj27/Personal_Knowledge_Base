# Personal Knowledge Base

A cloud-based document workspace that helps users store, organize, and search their personal files using AI.

The project combines a modern web interface with a secure backend, structured databases, cloud file storage, and AI-powered semantic search. It is designed as a practical production-style application and demonstrates how these technologies can work together in a real project.

> **Cloud storage environments**
>
> - **Development & Testing:** Backblaze B2
> - **Production:** AWS S3
>
> These are separate environments. Backblaze B2 is used while developing and testing the application, while AWS S3 is used for the production deployment.

---

## Key Features

- **User Authentication** — Users can register and log in securely. Passwords are protected and authenticated sessions use JWT-based access tokens.
- **Document Storage** — Users can upload and manage files in their personal document vault.
- **AI-Powered Search** — The application can understand the meaning of document content, allowing users to find relevant information without relying only on exact keywords.
- **Document Information Management** — File titles, descriptions, tags, ownership, and other information are stored separately from the actual files.
- **Fast Search and Responses** — Redis is used to cache frequently requested information and reduce unnecessary processing.
- **AI Knowledge Retrieval (RAG)** — Documents can be processed into smaller sections so the AI can retrieve relevant information and use it when answering user questions.
- **REST API** — The frontend communicates with the backend through a structured API covering authentication, document management, search, health checks, and AI/RAG operations.
- **Background Processing** — Document indexing and other longer-running tasks are handled in the background so normal application usage remains responsive.

---

## Technology Stack

### Frontend

| Category | Technology |
|---|---|
| Core Library | React 19 |
| Build Tool | Vite |
| UI Components | Material UI (MUI) v9, Emotion CSS |
| HTTP Client | Axios |
| State Management | React Context API |
| Testing | Vitest |
| Code Quality | ESLint |

### Backend

| Category | Technology |
|---|---|
| Language | Python 3.12+ |
| Framework | FastAPI |
| Database Access | SQLAlchemy 2.0 |
| Database Migrations | Alembic 1.19.1 |
| Validation & Configuration | Pydantic v2, Pydantic Settings |
| Authentication | JWT (HS256), Argon2id password hashing |
| API Server | Uvicorn for development, Gunicorn + Uvicorn workers for production |
| Testing | Pytest, pytest-asyncio, httpx |
| PDF Processing | PyMuPDF |
| File Upload Handling | python-multipart |

### Databases and Caching

| Purpose | Technology |
|---|---|
| Main Database | MySQL 8.0 |
| Vector Search Database | Qdrant |
| Caching | Redis 7 |

### Cloud and Infrastructure

| Purpose | Technology |
|---|---|
| **Production File Storage** | **AWS S3** |
| **Development & Testing File Storage** | **Backblaze B2** |
| Production Cloud Server | AWS EC2 |
| Containers | Docker, Docker Compose |
| AI Services | Google Gemini API |

### Development Tools

| Purpose | Technology |
|---|---|
| Python Package Management | pip, uv |
| Code Formatting | Black |
| Frontend Linting | ESLint |
| Configuration | Pydantic Settings, `.env` files |
| Local Environment | Docker Compose with health checks |

---

## Cloud Storage Setup

The project uses two different object-storage services for different environments.

### Development and Testing — Backblaze B2

**Backblaze B2** is used for local development and testing.

It provides the application with cloud-based file storage without using the production storage environment during development.

The application uses the S3-compatible API provided by Backblaze B2, which allows the same general upload approach to be used during development.

### Production — AWS S3

**AWS S3** is used for the production environment.

When the application is deployed for real users, uploaded files are stored in an AWS S3 bucket. AWS EC2 hosts the production application and communicates with S3 for file-storage operations.

### Environment Separation

| Environment | File Storage | Purpose |
|---|---|---|
| Development | Backblaze B2 | Building and testing the application |
| Production | AWS S3 | Storing files for the live application |

The application selects the appropriate storage service through environment configuration. **Backblaze B2 is not the production storage service, and AWS S3 is not the development storage service.**

---

## High-Level Architecture

The application follows a three-layer structure:

1. **Frontend** — Provides the user interface for login, file management, knowledge-base selection, and search.
2. **Backend** — Handles authentication, document management, search, AI processing, and communication with other services.
3. **Data and Cloud Services** — Store file information, files, search data, and cached results.

### Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLIENT (React + Vite)                           │
│                                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌──────────────────┐    │
│  │ AuthPage │  │  VaultPage   │  │ Knowledge │  │  SearchHeader    │    │
│  │ (Login/  │  │ (Document    │  │ Base Page │  │ (Semantic Search │    │
│  │ Register)│  │  List/Upload)│  │ (File     │  │   + Upload UI)   │    │
│  └────┬─────┘  └──────┬───────┘  └─────┬─────┘  └────────┬─────────┘    │
│       │               │                │                 │              │
│       └───────────────┴────────────────┴─────────────────┘              │
│                              │                                          │
│                       Axios (JWT Interceptors)                          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                          HTTPS / CORS
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       BACKEND (FastAPI + Gunicorn)                      │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      FastAPI App (main.py)                        │  │
│  │                                                                   │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐     │  │
│  │  │   Auth   │  │ Document │  │  Search  │  │      RAG       │     │  │
│  │  │  Routes  │  │  Routes  │  │  Routes  │  │     Routes     │     │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬────────┘     │  │
│  └───────┼─────────────┼─────────────┼────────────────┼────────────┘    │
│          │             │             │                │                 │
│  ┌───────▼─────────────▼─────────────▼────────────────▼────────────┐    │
│  │                        Services Layer                           │    │
│  │                                                                 │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐   │    │
│  │  │ Storage  │  │    AI    │  │  Cache   │  │   RAG Engine   │   │    │
│  │  │ Presigned│  │  Gemini  │  │  Redis   │  │   (Chunker,    │   │    │
│  │  │   URLs   │  │ Embedding│  │          │  │    Embedder,   │   │    │
│  │  │          │  │ /Generate│  │          │  │  Orchestrator) │   │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                       Core & Workers                              │  │
│  │                                                                   │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐     │  │
│  │  │  Config  │  │ Security │  │ Indexing │  │   RAG Workers  │     │  │
│  │  │(Settings)│  │   (JWT/  │  │  Worker  │  │   (Backfill,   │     │  │
│  │  │          │  │  Argon2) │  │          │  │    Re-index)   │     │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────────────┘     │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                  ┌────────────┼────────────┐
                  │            │            │
                  ▼            ▼            ▼
           ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
           │   MYSQL 8.0  │ │    QDRANT    │ │   REDIS 7    │
           │              │ │              │ │              │
           │   File/User  │ │ Vector Search│ │    Cache     │
           │   Metadata   │ │ & Embeddings │ │              │
           └──────────────┘ └──────────────┘ └──────────────┘
                  │
                  │
                  │ File Storage
                  ▼
           ┌───────────────────────────────────────────────┐
           │                OBJECT STORAGE                 │
           │                                               │
           │  Development & Testing → Backblaze B2         │
           │  Production            → AWS S3               │
           └───────────────────────────────────────────────┘
```

### How the Application Works

1. A user interacts with the application through the React frontend.
2. The frontend communicates with the FastAPI backend through secure API requests.
3. The backend verifies the user's access and handles the requested operation.
4. MySQL stores information about files, users, ownership, titles, descriptions, and tags.
5. The actual uploaded files are stored in the configured cloud storage:
   - **Backblaze B2 during development and testing**
   - **AWS S3 in production**
6. Qdrant stores information that helps the application perform meaning-based document searches.
7. Google Gemini is used to create document embeddings and generate AI responses.
8. Redis stores frequently used results to improve response speed.
9. Background workers process document indexing and RAG-related tasks without blocking normal application requests.

---

## Project Folder Structure

```text
Personal_Knowledge_Base/
│
├── backend/                              # FastAPI backend
│   ├── main.py                           # Application entry point
│   ├── alembic.ini                       # Database migration configuration
│   ├── pyproject.toml                    # Python project configuration
│   ├── requirements.txt                  # Python dependencies
│   ├── pytest.ini                        # Test configuration
│   ├── Dockerfile                        # Backend container configuration
│   │
│   ├── alembic/                          # Database migration files
│   │   ├── versions/                     # Migration scripts
│   │   ├── env.py                        # Migration environment
│   │   ├── script.py.mako                # Migration template
│   │   └── README                        # Alembic documentation
│   │
│   ├── app/                              # Main application package
│   │   ├── apis/routes/                  # API routes
│   │   ├── auth/                         # Authentication functions
│   │   ├── core/                         # Configuration and security
│   │   ├── database/                     # Database connections and models
│   │   ├── schemas/                      # Request and response validation
│   │   ├── services/                     # Main application services
│   │   │   ├── AWS/s3_service.py         # Cloud file-storage operations
│   │   │   ├── AI/vector_service.py      # Vector search operations
│   │   │   ├── AI/rag_vector_service.py  # RAG vector operations
│   │   │   ├── cache/redis_cache.py      # Redis caching
│   │   │   └── rag/                      # RAG processing modules
│   │   │       ├── rag_orchestrator.py   # RAG workflow
│   │   │       ├── chunker.py             # Document text splitting
│   │   │       ├── embedding.py            # Gemini embeddings
│   │   │       ├── generation.py           # Gemini AI responses
│   │   │       ├── pdf_extractor.py        # PDF text extraction
│   │   │       ├── qdrant_service.py       # Qdrant operations
│   │   │       ├── indexing_service.py     # Document indexing
│   │   │       └── ...                     # Supporting RAG utilities
│   │   │
│   │   ├── workers/                      # Background processing
│   │   │   ├── indexing_worker.py        # File indexing
│   │   │   └── rag_worker.py             # RAG processing
│   │   │
│   │   └── utils/                        # Utility functions
│   │
│   └── tests/                            # Backend tests
│       ├── integration/routes/            # API integration tests
│       ├── unit/services/                 # Service-level tests
│       └── test_auth_and_files.py         # Authentication and file tests
│
├── frontend/                             # React frontend
│   ├── package.json                       # Frontend dependencies
│   ├── vite.config.js                     # Vite configuration
│   ├── eslint.config.js                   # ESLint configuration
│   ├── index.html                         # Main HTML template
│   │
│   └── src/
│       ├── apis/                           # Backend API integration
│       │   ├── axiosClient.js              # Axios configuration
│       │   ├── authApi.js                  # Authentication API
│       │   ├── documentApi.js              # Document API
│       │   ├── ragApi.js                   # RAG API
│       │   └── systemApi.js                # System health API
│       │
│       ├── components/                     # Reusable UI components
│       │   ├── SearchHeader.jsx             # Search and upload interface
│       │   ├── FileList.jsx                 # File list
│       │   ├── FileRow.jsx                  # Individual file row
│       │   ├── Header.jsx                   # Application header
│       │   ├── RagMessageBubble.jsx         # AI response display
│       │   ├── DeleteConfirmDialog.jsx      # Delete confirmation
│       │   ├── EditMetadataDialog.jsx       # Metadata editing
│       │   └── SelectionToolbar.jsx         # Bulk selection
│       │
│       ├── pages/                          # Main application pages
│       │   ├── AuthPage.jsx                 # Login and registration
│       │   ├── VaultPage.jsx                # Document vault
│       │   └── KnowledgeBase.jsx            # Knowledge base
│       │
│       ├── context/                        # Shared application state
│       │   └── KnowledgeBaseFilesContext.jsx
│       │
│       ├── services/                       # Frontend services
│       │   └── authService.js               # Authentication state
│       │
│       ├── assets/                         # Images and icons
│       ├── App.jsx                          # Root application
│       ├── App.css                          # Application styles
│       ├── index.css                        # Global styles
│       └── main.jsx                         # React entry point
│
├── docker-compose.yml                      # Local multi-service setup
├── documentation/                          # Project documentation
├── others/                                 # Environment and configuration files
└── README.md                               # Project overview
```

---

## Project Purpose

The Personal Knowledge Base is designed to demonstrate a complete modern software application rather than a simple file-upload system.

The project brings together:

- A responsive web interface
- Secure user authentication
- Cloud-based document storage
- Structured document and user information
- AI-powered search
- AI-assisted question answering
- Background document processing
- Containerized application services
- Separate development and production cloud environments

This makes the project a practical example of how a full-stack application can be designed, developed, tested, and prepared for production deployment.

---

## License

This project is open-source and available under the [MIT License](LICENSE).
