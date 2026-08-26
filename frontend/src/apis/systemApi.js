import axiosClient from './axiosClient'

/**
 * Check the connection status of the backend API.
 * @returns {Promise<{ status: string, message: string }>}
 */
export const pingSystem = () => {
  return axiosClient.get('/system/ping')
}
