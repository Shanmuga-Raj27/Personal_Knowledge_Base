import axiosClient from './axiosClient'

/**
 * Register a new user account.
 * 
 * @param {string} email - User registration email.
 * @param {string} password - Account password (min length 8).
 * @param {string} confirmPassword - Password confirmation matching password.
 * @returns {Promise<object>} Returns the registered user profile details.
 */
export const registerUser = (email, password, confirmPassword) => {
  return axiosClient.post('/auth/register', {
    email,
    password,
    confirm_password: confirmPassword,
  })
}

/**
 * Log in to an existing user account and request a JWT token.
 * 
 * @param {string} email - Account email.
 * @param {string} password - Account password.
 * @returns {Promise<object>} Returns JWT credentials payload containing access_token.
 */
export const loginUser = (email, password) => {
  return axiosClient.post('/auth/login', {
    email,
    password,
  })
}

/**
 * Verify OTP code to complete registration and receive JWT credentials.
 * 
 * @param {string} email - Account email.
 * @param {string} otp - 6-digit verification code.
 * @returns {Promise<object>} Returns JWT credentials payload containing access_token.
 */
export const verifyOtp = (email, otp) => {
  return axiosClient.post('/auth/verify-otp', {
    email,
    otp,
  })
}

/**
 * Resend a fresh OTP verification code to the given email.
 * 
 * @param {string} email - Account email.
 * @returns {Promise<object>} Returns confirmation message payload.
 */
export const resendOtp = (email) => {
  return axiosClient.post('/auth/resend-otp', {
    email,
  })
}

