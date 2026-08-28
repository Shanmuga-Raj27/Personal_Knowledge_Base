# Implementation Plan - Phase 6.1: React MUI Register/Login UI & API Integration

This document outlines the React frontend architecture, Material-UI (MUI) components design system, axios client updates, stateless token management services, and integration routing flow to enable secure user registration and login in the Personal Knowledge Base client.

---

## 1. Goals & Architectural Choices

### Primary Objectives
- **Modern Minimalist UI**: Design clean, responsive Login and Register interfaces strictly using React MUI (no custom CSS, styled-components, or Tailwind CSS).
- **Stateless Session Storage**: Save JWT access tokens in client `localStorage`. Since tokens are short-lived, client-side logout will simply remove the stored token.
- **Separation of Concerns**: Decouple the React views from raw network calls, API endpoint configurations, and localStorage utilities.
- **Robust HTTP Interceptor Pipeline**: Automatically attach Bearer credentials to outgoing document requests and gracefully evict user sessions upon encountering `401 Unauthorized` responses.

---

## 2. File & Component Specifications

### A. Centralized API Interceptors (`frontend/src/apis/`)

#### 1. Axios Client Update (`axiosClient.js`)
Refactor the current request and response interceptors:
- **Request Interceptor**:
  - Dynamically import and invoke `authService.getToken()`.
  - If a token exists, inject `config.headers.Authorization = `Bearer ${token}``.
- **Response Interceptor**:
  - Catch API error status codes. If `error.status === 401`:
    - Invoke `authService.clearToken()`.
    - Reset the React state (e.g. via a global callback or custom event) to force a logout transition.

#### 2. Auth Endpoint Router (`authApi.js` - NEW)
Define axios calls matching the backend authentication routes:
- `registerUser(payload)`: Sends a `POST` request to `/auth/register` containing `email`, `password`, and `confirm_password`.
- `loginUser(payload)`: Sends a `POST` request to `/auth/login` containing `email` and `password`.

---

### B. Stateless Session Service (`frontend/src/services/`)

#### 1. Authentication Service (`authService.js` - NEW)
Implement utilities to decouple localStorage operations from React components:
- `saveToken(token)`: Saves the JWT token to `localStorage` under `token_key`.
- `getToken()`: Fetches the JWT token string from `localStorage`.
- `clearToken()`: Removes the JWT token key from `localStorage`.
- `decodeToken(token)`: decodes the JWT base64 payload to retrieve the subject numeric user ID (`sub`), expiration timestamp (`exp`), and other user scopes.
- `isAuthenticated()`: Evaluates token validity by asserting the token is present and the current timestamp has not exceeded `exp`.

---

### C. Authentication Page (`frontend/src/pages/`)

#### 1. Authentication Component (`AuthPage.jsx` - NEW)
Develop a minimalist centered view using strict MUI elements:
- **Structure**: Center-aligned vertically and horizontally using `<Box sx={{ display: 'flex', minHeight: '100vh', alignItems: 'center' }}>`.
- **Theme Boundaries**: Inherits Outfit typography and colors from `ThemeProvider`.
- **Forms**:
  - **Login Form**: Email field (validated format), password field with a toggle visibility button, and a primary action button.
  - **Register Form**: Email field, password field (enforces min length of 8), confirm password field, and a register button.
- **Form State Validation**:
  - Validates `password === confirm_password` before sending requests.
  - Renders a clean error `<Alert>` banner in the form if validations fail.
  - Disables submit buttons during pending requests.

---

### D. Header & Dashboard Scoping (`frontend/src/components/`, `frontend/src/App.jsx`)

#### 1. Header Updates (`Header.jsx`)
Update the Navigation Header to accept user session props:
- Add props: `currentUser` (containing `email`) and `onLogout`.
- **Authenticated view**:
  - Display the logged-in email and a generic profile Avatar button.
  - Clicking the Avatar opens a MUI `<Menu>` with user status details and a clickable **Logout** action.

#### 2. Root App Controller (`App.jsx`)
Integrate session state logic at the root React component:
- Define states: `token`, `currentUser`, and `isAuthenticated`.
- Initialize state check: on mount, verify token existence and expiration. If valid, load the profile details into `currentUser`.
- **Conditional Layout Routing**:
  - If `isAuthenticated` is true, render `<Header currentUser={currentUser} onLogout={handleLogout} />` and the `<SearchHeader />`/`<FileList />` semantic search dashboard.
  - If `isAuthenticated` is false, render `<AuthPage onLoginSuccess={handleLoginSuccess} />`.

---

## 3. Exclusions (Out of Scope for Phase 6.1)
- ❌ Third-party state management libraries (Redux, Zustand).
- ❌ External router packages (React Router, conditional state routing only).
- ❌ Third-party form libraries (Formik, React Hook Form).
- ❌ Global CSS styling overrides or external style imports.

---

## 4. Verification Plan

### Manual Verification Flow
1. **Redirection Guard**: Clear local storage, open the site, and verify the app opens on `<AuthPage>` and blocks access to files.
2. **Client Validation**: Attempt to submit registration with mismatched passwords or passwords less than 8 characters, checking that the `<Alert>` warns the user.
3. **Session Establishment**: Log in with correct credentials, checking that the app transition to the file dashboard is instant and the header displays the email.
4. **Interception Check**: Check the network tab during a search or file download to verify the header `Authorization: Bearer <token>` is present in API calls.
5. **Session Expiration Action**: Manually set the stored token to an expired state in browser developer tools, perform a file update, and check that the app automatically logs out.
