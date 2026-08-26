import axios from 'axios'

// Create a centralized Axios instance
const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 10000, // 10 seconds timeout
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})

// Request Interceptor: can be used to add Authorization headers (e.g. JWT tokens) in later phases
axiosClient.interceptors.request.use(
  (config) => {
    // Add logic here if needed (e.g., token insertion)
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
    // Return only the response data directly
    return response.data
  },
  (error) => {
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
