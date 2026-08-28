/**
 * frontend/src/services/authService.js
 * 
 * Stateless session helper utilities to manage JWT tokens in client localStorage.
 */

const TOKEN_KEY = 'pkb_access_token'

/**
 * Save JWT access token to localStorage.
 */
export const saveToken = (token) => {
  localStorage.setItem(TOKEN_KEY, token)
}

/**
 * Retrieve JWT access token from localStorage.
 */
export const getToken = () => {
  return localStorage.getItem(TOKEN_KEY)
}

/**
 * Evict JWT access token from localStorage.
 */
export const clearToken = () => {
  localStorage.removeItem(TOKEN_KEY)
}

/**
 * Decode a base64 JWT payload safely supporting UTF-8 characters.
 */
export const decodeToken = (token) => {
  if (!token) return null
  try {
    const base64Url = token.split('.')[1]
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      window.atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    )
    return JSON.parse(jsonPayload)
  } catch (err) {
    console.error('Failed to decode JWT token:', err)
    return null
  }
}

/**
 * Check if the stored JWT is valid and unexpired.
 */
export const isAuthenticated = () => {
  const token = getToken()
  if (!token) return false

  const decoded = decodeToken(token)
  if (!decoded || !decoded.exp) return false

  const now = Math.floor(Date.now() / 1000)
  return now < decoded.exp
}
