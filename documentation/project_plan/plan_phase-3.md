# Phase 3 Project Plan: Connecting Frontend & Backend

Welcome to Phase 3! Now that we have our React frontend UI created and our FastAPI backend ready, we need to build the "bridge" that allows them to talk to each other securely and efficiently. 

Think of this phase as laying down the telephone wires and establishing the security protocols between two cities.

---

## 1. Executive Summary & Objective

In this phase, we are moving from static components to a dynamic, connected system. 
* **The Goal**: Enable our React frontend to request, receive, and send data to our FastAPI backend.
* **The Challenge**: Browsers are highly protective. They don't just let any random website talk to any random backend. We must explicitly configure security settings (CORS) on the backend and build a robust, organized communication manager (Axios) on the frontend.

By the end of this phase, clicking a button in React will trigger a clean, formatted request to FastAPI, which will process the request and securely send back the data.

---

## 2. Backend Concepts Explained Simply

Before writing code, let’s understand how the backend manages and secures inbound requests.

### What is CORS (Cross-Origin Resource Sharing)?
Imagine you are at a high-security office building. 
* Your React app runs at `http://localhost:5173`.
* Your FastAPI backend runs at `http://localhost:8000`.

Even though they are both on your computer, the browser treats them as completely different "origins" (different domains/ports). 

By default, web browsers block websites from making requests to a different domain to prevent malicious scripts from stealing your data. For example, if you are logged into **Gmail** in one tab, a malicious game website in another tab shouldn't be allowed to secretly send requests to Gmail's servers to read your emails. 

**CORS** is the protocol where our backend explicitly tells the browser: *"Hey, I know `http://localhost:5173`. They are friendly. You have my permission to let them talk to me and access my data."*

### What is Middleware?
In simple terms, middleware is code that runs **in the middle** of a request-response cycle. When a request is sent from the frontend to the backend, it doesn't immediately execute your route logic (like fetching a file or authenticating a user). Instead, it passes through one or more layers of middleware first.

Think of it like a security screening line at an airport:
1. **The Request (Passenger)** arrives at the airport.
2. **The Middleware (Security Checkpoint)** intercepts the passenger. It inspects their ID, verifies they have a valid ticket, and runs them through a scanner.
3. If everything is valid, the passenger is allowed to proceed to their **Flight (the backend Endpoint / Route handler)**. If something is invalid (e.g., they don't have permission), they are stopped and turned back immediately.

Why is this useful?
* **Security & Authentication**: You can write a middleware to check if a user is logged in *before* letting them access private database endpoints.
* **CORS**: It checks if the origin domain making the request is whitelisted.
* **Logging & Performance**: It can log how long each request took to process.

Here is the sequence of how a request travels through the system:

```text
[React Frontend (Port 5173)]
       │
       │ (1) Sends HTTP Request
       ▼
[Web Browser] ──(2) Sends Pre-flight CORS Check──► [FastAPI Backend]
       │                                                  │
       │                                       (3) CORS Middleware checks whitelist
       │                                                  │
       │◄─(4) Returns Approval (CORS headers) ◄───────────┘
       ▼
[Web Browser] ──(5) Sends Actual Request data ──► [FastAPI Middleware Checkpoint]
                                                          │
                                                (6) If valid, forwards to...
                                                          │
                                                          ▼
                                                  [Backend Route handler]
                                                          │
                                                (7) Processes business/DB logic
                                                          │
                                                          ▼
[React Frontend] ◄──────(8) Sends back Response ◄─────────┘
```

### How CORS and Middleware Work Together in FastAPI
FastAPI has a built-in `CORSMiddleware`. We configure it at the very top of our application. Every single request sent to our backend passes through this middleware first. If the incoming request comes from an origin we didn't whitelist, the middleware blocks it, protecting our database and services.

---

## 3. Frontend Concepts Explained Simply

Now, let's look at how the frontend initiates this conversation.

### What is Data Fetching?
Think of data fetching like ordering food on **UberEats**. 
Your phone app doesn't have a kitchen or food inside it. Instead, when you click "Order", the app sends a request over the internet to the restaurant's kitchen (the backend/database). Once the food is ready, it is delivered back to your app, and you see "Order Delivered". 

In web development, React is the phone app UI, and data fetching is the process of asking the FastAPI server for data (like user profiles or documents) and displaying it on the screen.

### Axios vs. Fetch API: The Car Analogy
To fetch data, Javascript has a built-in tool called `fetch()`. However, many developers prefer a library called `Axios`.

| Feature | `fetch()` (Built-in) | `Axios` (Third-Party Library) |
| :--- | :--- | :--- |
| **Analogy** | **A standard, default city bicycle.** It is free and built-in, but you have to manually buy and install headlights, a basket, and a phone mount yourself. | **A premium electric scooter.** It comes pre-equipped with headlights, GPS navigation, and automatic speed control out of the box. |
| **Error Handling** | Doesn't automatically catch HTTP errors (like 404 Not Found or 500 Server Error). You have to write extra code to catch them. | Automatically throws an error if the server returns a bad status code. |
| **Request Setup** | You have to manually convert your objects to JSON strings every single time (`JSON.stringify(data)`). | Automatically converts data to JSON for you. |
| **Interceptors** | Hard to implement global behavior (like automatically attaching a login token to every request). | Extremely simple to intercept and modify requests globally. |

### Why We Use Axios in Our Project
We use Axios because it allows us to set up a **central client config**. We configure our base URL (`http://localhost:8000`) once, and every API call we make throughout the app automatically inherits it. If we need to send login tokens with our requests later, we can write an interceptor in one file instead of changing 50 different component files.

---

## 4. Architecture & Directory Structure (Production Standards)

To keep our project clean, organized, and scalable as we grow, we use the **Separation of Concerns** principle. We separate configuration, routes, and API calls into their own dedicated folders.

### Frontend API Folder Structure
Instead of making API calls directly inside component files (like `App.jsx`), we organize them in a dedicated `apis/` directory:

```text
frontend/src/
├── apis/
│   ├── axiosClient.js       <-- Central Axios setup (base URL, headers, interceptors)
│   ├── authApi.js           <-- All endpoints related to login, signup, password resets
│   └── documentApi.js       <-- All endpoints related to documents and knowledge base
├── components/
└── App.jsx                  <-- Only import functions from apis/ files to display data
```

### Backend Directory Structure
To keep our application tidy, we avoid putting all of our routing, database, and logic inside a single `main.py` file. Instead, we use the following directory layout:

```text
backend/
├── main.py                  <-- Entrypoint; initializes FastAPI, applies CORS middleware, registers routes
├── app/
│   ├── apis/
│   │   └── routes/
│   │       └── upload_file.py <-- Endpoint routes (e.g., file upload handlers)
│   ├── auth/
│   │   └── auth.py          <-- Authentication routes and handling
│   ├── core/
│   │   ├── config.py        <-- Handles config, environment vars, and whitelisted CORS origins
│   │   └── security.py      <-- Hashing, JWT creation, verification, and security helpers
│   ├── database/
│   │   ├── database.py      <-- SQLAlchemy connection and db session setup
│   │   └── db_models.py     <-- SQLAlchemy Database Models (how tables look in MySQL)
│   ├── schemas/
│   │   ├── file.py          <-- Pydantic schemas for file response/request details
│   │   └── schemas.py       <-- Pydantic schemas for user and schema data validations
│   ├── services/
│   │   ├── AI/              <-- Services interacting with the Gemini API
│   │   └── AWS/             <-- Services interacting with AWS S3 buckets
│   └── utils/               <-- Custom helper functions used across the application
```

### Why is this the Production Standard?
* **Maintainability**: If the backend URL changes, you only update `axiosClient.js` once, not every page.
* **Team Collaboration**: One developer can work on React UI components while another writes the backend routers without causing file conflicts.
* **Testability**: You can test API functions in isolation without rendering the entire UI.

---

## 5. Step-by-Step Implementation Roadmap

We will connect the frontend and backend in three structured stages:

### Step 1: Config CORS on the Backend
1. Open `backend/app/core/config.py` and define an allowed origins list (e.g., `["http://localhost:5173"]`).
2. Open `backend/app/main.py`.
3. Import `CORSMiddleware` from `fastapi.middleware.cors`.
4. Apply the middleware to the FastAPI app, linking it to the allowed origins list.

### Step 2: Establish Axios on the Frontend
1. Install axios in the frontend (`npm install axios`).
2. Create `src/apis/axiosClient.js`. Configure the instance with the base URL pointing to the FastAPI server.
3. Create a test API function (e.g., `src/apis/systemApi.js`) containing a function to call a simple health check `/ping` endpoint.

### Step 3: Connect and Verify
1. In `App.jsx`, call the health check function when the page loads (using `useEffect`).
2. Start both servers:
   * FastAPI: `uvicorn app.main:app --reload` (usually Port 8000)
   * React: `npm run dev` (usually Port 5173)
3. Open your browser's Developer Tools (`F12` -> Network tab).
4. Refresh the page and look for the API call to verify a successful status code (`200 OK`) and confirm there are no CORS error blocks.
