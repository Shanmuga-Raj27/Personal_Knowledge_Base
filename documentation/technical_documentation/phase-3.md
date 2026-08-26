# Phase 3 Technical Documentation: Secure Direct Storage & Frontend-Backend Integration

Welcome to the technical documentation for **Phase 3** of the Personal Knowledge Base (PKB) project. In this phase, we moved our codebase from isolated components to a connected, secure, and production-ready application. 

This guide is designed to explain the architecture, the integration patterns we used, and how we solved security issues like CORS.

---

## 1. Executive Summary & Phase Objective

The objective of Phase 3 was to build a secure, efficient communication bridge between our React frontend UI and our FastAPI backend, enabling direct-to-storage file uploads to Backblaze B2.

```text
[ React Frontend ] ──────(1) Requests Upload URL─────► [ FastAPI Backend ]
        │                                                     │
        │◄──────(2) Returns Presigned S3 PUT URL ─────────────┘
        │
        └───────(3) Uploads File Directly ──────────────────► [ Backblaze B2 S3 ]
```

### Why Upload Directly to S3/B2? (The Senior Dev Architecture)
In basic web applications, files are uploaded to the backend server, which then saves them to disk or forwards them to storage. 
* **The Problem:** Processing files on the backend server consumes valuable CPU cycles, memory (RAM), and network bandwidth. If 100 users upload large PDFs at the same time, the backend server will slow down or crash.
* **The Solution (Direct Upload):** The frontend asks the FastAPI backend for a temporary, secure **Presigned URL**. The browser then uses this URL to upload the file directly to Backblaze B2. Our backend server is never choked by handling raw file bytes, making the system highly scalable.

---

## 2. Backend Architecture & Connection Logic

### What is CORS (Cross-Origin Resource Sharing)?
> [!TIP]
> **The Office Analogy:** Imagine you work in a high-security office building (FastAPI, Port 8000). A messenger from a different company (React UI, Port 5173) arrives at your front desk asking for client files. To protect your data, your receptionist blocks them by default. **CORS** is the system where you officially whitelist the friendly company's messenger, giving them permission to enter and request files.

By default, modern web browsers prevent code running on one domain (origin) from interacting with resources on another domain. Because our frontend runs on `http://localhost:5173` and our backend runs on `http://localhost:8000`, the browser views them as completely separate origins and blocks communications unless we configure CORS.

We configured the whitelisted origins in the backend Settings class:
```python
# app/core/config.py
class Settings(BaseSettings):
    # Load configuration from environment files
    model_config = SettingsConfigDict(env_file="../others/.env", extra="ignore")
    
    # Whitelisted CORS origins
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
```

### What is Middleware?
> [!TIP]
> **The Airport Security Checkpoint Analogy:** Middleware is code that runs **in the middle** of the request-response lifecycle. It is like the security screening line at the airport. Before a passenger (HTTP request) is allowed to board their flight (endpoint handler), the security guards (middleware) inspect their ticket and ID. If they fail the check, they are rejected immediately.

FastAPI provides a built-in `CORSMiddleware` that intercepts every incoming request. We registered it in [main.py](file:///d:/Personal_Knowledge_Base/backend/main.py) to check the origin of incoming requests against our whitelist:

```python
# main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # Whitelisted domains
    allow_credentials=True,               # Allow cookies / authentication headers
    allow_methods=["*"],                  # Allow all standard HTTP actions (GET, POST, etc.)
    allow_headers=["*"],                  # Allow all standard headers
)
```

### Health Check Endpoint
To allow the frontend to confirm that the backend is online and running, we created a dedicated diagnostic router in [system.py](file:///d:/Personal_Knowledge_Base/backend/app/apis/routes/system.py) exposing a `/system/ping` endpoint:

```python
# app/apis/routes/system.py
@router.get("/ping")
async def ping():
    return {"status": "ok", "message": "pong"}
```

---

## 3. Frontend API Integration (Axios Architecture)

### Axios vs. Fetch API
To fetch data from our API, we chose **Axios** over the browser's built-in `fetch()` tool.
* **The City Bicycle Analogy:** `fetch()` is like a standard city bicycle. It is free and functional, but you have to manually configure lights, GPS, and security locks yourself.
* **The Electric Scooter Analogy:** `Axios` is like a premium electric scooter. It comes pre-equipped with advanced features out-of-the-box, such as automatic JSON conversion, timeout limits, and global request/response interception.

### Centralized Axios Client Setup
We created a single shared instance in [axiosClient.js](file:///d:/Personal_Knowledge_Base/frontend/src/apis/axiosClient.js) that configures the base API URL dynamically (falling back to localhost if no environment variable is provided):

```javascript
// src/apis/axiosClient.js
const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})
```

We attached a **Response Interceptor** to automatically unpack the response data payload or catch HTTP status errors (like `404 Not Found` or `500 Server Error`) and format them into clear JavaScript errors.

### Decoupled API Modules
Instead of making API requests directly inside React components, we separated them into clean, modular files inside the `src/apis/` directory:
1. [systemApi.js](file:///d:/Personal_Knowledge_Base/frontend/src/apis/systemApi.js): Exports `pingSystem()` to query backend connection health.
2. [documentApi.js](file:///d:/Personal_Knowledge_Base/frontend/src/apis/documentApi.js): Exports `getUploadUrl(filename, contentType)` to request pre-signed upload URLs from FastAPI.

---

## 4. The Big Challenge: The Backblaze B2 CORS Problem

### What Happened?
During our initial direct-to-S3 uploads, the frontend reported a network upload error:
`Access to XMLHttpRequest at 'https://s3.eu-central-003.backblazeb2.com/...' has been blocked by CORS policy.`

### What Caused It?
Even though our FastAPI backend whitelist was configured correctly, the browser was uploading the file *directly* to Backblaze B2 S3 storage. Therefore, the browser made a preflight `OPTIONS` request directly to Backblaze. Because our storage bucket did not have a CORS configuration rule, Backblaze rejected the preflight check, and the browser blocked the subsequent file upload.

### How We Fixed It (The Principle of Least Privilege)
We did not use generic preset rules like *"Share everything in this bucket with every origin"*, as this would allow any malicious script on the web to make calls to our storage. 

Instead, we wrote a secure administration script [set_cors_secure.py](file:///d:/Personal_Knowledge_Base/backend/app/scripts/set_cors_secure.py) using `boto3` to apply a strict, custom CORS policy to our bucket:
* **Allowed Origin**: Restricted exclusively to `http://localhost:5173` (our local development port).
* **Allowed Method**: Restricted exclusively to `PUT` requests (only allowing files to be written; no browser-based listing, reading, or deleting of files is permitted).
* **Allowed Headers**: Restricted to `content-type` to prevent extra headers from being sent.

---

## 5. Key Code Snippets

### A. Secure S3 Bucket CORS Configuration (Python)
This configuration was applied programmatically to the Backblaze B2 bucket:
```python
cors_configuration = {
    'CORSRules': [
        {
            'AllowedHeaders': ['content-type'],
            'AllowedMethods': ['PUT'],                     # Only allow uploads
            'AllowedOrigins': ['http://localhost:5173'],   # Only allow local React app
            'ExposeHeaders': ['ETag'],
            'MaxAgeSeconds': 3600
        }
    ]
}

s3.put_bucket_cors(
    Bucket="<YOUR_S3_BUCKET_NAME>",
    CORSConfiguration=cors_configuration
)
```

### B. Axios Response Interceptor (JavaScript)
Extracts the clean data payload or structures connection errors:
```javascript
axiosClient.interceptors.response.use(
  (response) => {
    // Automatically extract data from axios response wrapper
    return response.data
  },
  (error) => {
    // Format error payload cleanly
    const customError = {
      message: error.response?.data?.detail || error.message || 'An unexpected error occurred.',
      status: error.response?.status,
    }
    console.error('[API Response Error]', customError)
    return Promise.reject(customError)
  }
)
```

### C. Connection Health Indicator Dot Logic (React)
Monitors connection status on mount and styles the pulsing status badge inside the AppBar:
```jsx
// src/App.jsx
const [backendStatus, setBackendStatus] = useState('checking')

useEffect(() => {
  const checkConnection = async () => {
    try {
      await pingSystem()
      setBackendStatus('online')
    } catch (err) {
      setBackendStatus('offline')
    }
  }
  checkConnection()
}, [])
```
```jsx
// Visual Status Dot markup
<Box
  sx={{
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor:
      backendStatus === 'online'
        ? 'success.main'
        : backendStatus === 'offline'
        ? 'error.main'
        : 'warning.main',
    mr: 1,
    boxShadow:
      backendStatus === 'online'
        ? '0 0 8px rgba(46, 125, 50, 0.5)'
        : '0 0 8px rgba(211, 47, 47, 0.5)'
        : '0 0 8px rgba(237, 108, 2, 0.5)',
    animation: backendStatus === 'checking' ? 'pulse 1.5s infinite' : 'none',
    '@keyframes pulse': {
      '0%': { transform: 'scale(0.8)', opacity: 0.5 },
      '50%': { transform: 'scale(1.2)', opacity: 1 },
      '100%': { transform: 'scale(0.8)', opacity: 0.5 },
    },
  }}
/>
```
