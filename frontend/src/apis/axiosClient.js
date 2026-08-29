import axios from 'axios'
import { getToken, clearToken } from '../services/authService'

// Create a centralized Axios instance
const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 10000, // 10 seconds timeout
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})

// Request Interceptor: Inject JWT token automatically
axiosClient.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    console.error('[API Request Error]', error)
    return Promise.reject(error)
  }
)

// Response Interceptor: handle global response statuses and extract data
axiosClient.interceptors.response.use(
  (response) => {
    // Return response data directly, attaching fallback header metadata if present
    if (response.headers && response.headers['x-search-fallback'] === 'true' && typeof response.data === 'object' && response.data !== null) {
      response.data.isFallbackSearch = true
    }
    return response.data
  },
  (error) => {
    if (axios.isCancel(error)) {
      return Promise.reject(error)
    }

    // Check if the response was unauthorized (401)
    if (error.response?.status === 401) {
      console.warn('[API Session Expired] Evicting credentials.')
      clearToken()
      
      // Force page reload to clear all state variables and redirect to login
      if (typeof window !== 'undefined') {
        window.location.reload()
      }
    }

    // Log error details globally for easier debugging
    const customError = {
      message: error.response?.data?.detail || error.message || 'An unexpected error occurred.',
      status: error.response?.status,
      data: error.response?.data,
    }
    console.error('[API Response Error]', customError)
    return Promise.reject(customError)
  }
)

export default axiosClient
