import React, { useState, useEffect } from 'react'
import {
  Box,
  Container,
  Card,
  CardContent,
  TextField,
  Button,
  IconButton,
  InputAdornment,
  Typography,
  Alert,
  CircularProgress,
  useTheme,
  Stack,
} from '@mui/material'
import Visibility from '@mui/icons-material/Visibility'
import VisibilityOff from '@mui/icons-material/VisibilityOff'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import MarkEmailReadOutlinedIcon from '@mui/icons-material/MarkEmailReadOutlined'
import { loginUser, registerUser, verifyOtp, resendOtp } from '../apis/authApi'
import { SwanLogo } from './LandingPage'

export default function AuthPage({ onLoginSuccess, onBackToLanding, initialMode = 'login' }) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const [isLogin, setIsLogin] = useState(initialMode !== 'register')
  const [isVerifyingOtp, setIsVerifyingOtp] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [otp, setOtp] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [resendLoading, setResendLoading] = useState(false)
  const [cooldownSeconds, setCooldownSeconds] = useState(0)
  const [error, setError] = useState(null)
  const [successMsg, setSuccessMsg] = useState(null)

  // 60-second cooldown timer countdown effect
  useEffect(() => {
    if (cooldownSeconds <= 0) return
    const timer = setInterval(() => {
      setCooldownSeconds((prev) => (prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(timer)
  }, [cooldownSeconds])

  const toggleAuthMode = () => {
    setIsLogin(!isLogin)
    setIsVerifyingOtp(false)
    setError(null)
    setSuccessMsg(null)
    setOtp('')
    setPassword('')
    setConfirmPassword('')
  }

  const handleBackToRegister = () => {
    setIsVerifyingOtp(false)
    setOtp('')
    setError(null)
    setSuccessMsg(null)
  }

  const validateEmail = (input) => {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return re.test(input)
  }

  const validatePasswordComplexity = (pw) => {
    if (pw.length < 8) {
      return 'Password must be at least 8 characters long.'
    }
    if (!/[A-Z]/.test(pw)) {
      return 'Password must contain at least one uppercase letter.'
    }
    if (!/[a-z]/.test(pw)) {
      return 'Password must contain at least one lowercase letter.'
    }
    if (!/\d/.test(pw)) {
      return 'Password must contain at least one number.'
    }
    if (!/[!@#$%^&*(),.?":{}|<>_~`+\-=\[\]\\;/]/.test(pw)) {
      return 'Password must contain at least one special symbol.'
    }
    return null
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setSuccessMsg(null)

    // Flow 1: OTP Verification Submission
    if (isVerifyingOtp) {
      const cleanOtp = otp.trim()
      if (cleanOtp.length !== 6) {
        setError('Please enter the complete 6-digit verification code.')
        return
      }

      setLoading(true)
      try {
        const response = await verifyOtp(email.trim().toLowerCase(), cleanOtp)
        if (response && response.access_token) {
          onLoginSuccess(response.access_token, email.trim().toLowerCase())
        } else {
          throw new Error('Invalid verification response from server.')
        }
      } catch (err) {
        console.error('OTP Verification error:', err)
        setError(err.response?.data?.detail || err.message || 'Verification failed. Please try again.')
      } finally {
        setLoading(false)
      }
      return
    }

    // Client-side validations for Login & Registration
    if (!email.trim() || !password) {
      setError('Please fill in all required fields.')
      return
    }

    if (!validateEmail(email.trim())) {
      setError('Please enter a valid email address.')
      return
    }

    if (!isLogin) {
      const passwordError = validatePasswordComplexity(password)
      if (passwordError) {
        setError(passwordError)
        return
      }

      if (password !== confirmPassword) {
        setError('Passwords do not match.')
        return
      }
    }

    setLoading(true)
    try {
      if (isLogin) {
        // Authenticate User
        const response = await loginUser(email.trim().toLowerCase(), password)
        if (response && response.access_token) {
          onLoginSuccess(response.access_token, email.trim().toLowerCase())
        } else {
          throw new Error('Invalid authentication response from server.')
        }
      } else {
        // Register User (Initiate OTP Email)
        const response = await registerUser(email.trim().toLowerCase(), password, confirmPassword)
        setIsVerifyingOtp(true)
        setCooldownSeconds(60)
        setSuccessMsg(
          response?.message || 'Verification code sent! Please check your email inbox (valid for 10 minutes).'
        )
        setPassword('')
        setConfirmPassword('')
      }
    } catch (err) {
      console.error('Auth request error:', err)
      setError(err.response?.data?.detail || err.message || 'Authentication request failed. Please check credentials.')
    } finally {
      setLoading(false)
    }
  }

  const handleResendOtp = async () => {
    if (cooldownSeconds > 0 || resendLoading) return
    setError(null)
    setSuccessMsg(null)
    setResendLoading(true)

    try {
      const response = await resendOtp(email.trim().toLowerCase())
      setCooldownSeconds(60)
      setSuccessMsg(response?.message || 'A fresh verification code has been sent to your email.')
    } catch (err) {
      console.error('Resend OTP error:', err)
      setError(err.response?.data?.detail || err.message || 'Failed to resend code. Please try again.')
    } finally {
      setResendLoading(false)
    }
  }

  return (
    <Container
      maxWidth="xs"
      sx={{
        minHeight: '85vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        py: 6,
      }}
    >
      {/* Back to landing button */}
      {onBackToLanding && (
        <Box sx={{ width: '100%', mb: 2 }}>
          <Button
            startIcon={<ArrowBackIcon fontSize="small" />}
            onClick={onBackToLanding}
            size="small"
            sx={{
              color: theme.palette.text.secondary,
              fontWeight: 600,
              fontSize: '0.85rem',
              '&:hover': {
                color: '#FF6B00',
                backgroundColor: 'transparent',
              },
            }}
          >
            Back to Swan Drive
          </Button>
        </Box>
      )}

      <Card
        sx={{
          width: '100%',
          borderRadius: '16px',
          border: `1px solid ${theme.palette.divider}`,
          backgroundColor: theme.palette.background.paper,
          boxShadow: isDark
            ? '0 10px 25px -5px rgba(0, 0, 0, 0.5)'
            : '0 10px 25px -5px rgba(0, 0, 0, 0.04)',
        }}
      >
        <CardContent sx={{ p: { xs: 3.5, sm: 4.5 } }}>
          {/* Brand & Heading */}
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', mb: 3 }}>
            <Box sx={{ mb: 1.5 }}>
              {isVerifyingOtp ? (
                <Box
                  sx={{
                    width: 48,
                    height: 48,
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    backgroundColor: isDark ? 'rgba(255, 107, 0, 0.15)' : '#FFF7ED',
                    color: '#FF6B00',
                  }}
                >
                  <MarkEmailReadOutlinedIcon sx={{ fontSize: 28 }} />
                </Box>
              ) : (
                <SwanLogo size={38} />
              )}
            </Box>
            <Typography
              variant="h5"
              sx={{
                fontFamily: "Georgia, 'Times New Roman', Cambria, serif",
                fontWeight: 700,
                color: isDark ? '#FFFFFF' : '#0A0A0A',
                textAlign: 'center',
              }}
            >
              {isVerifyingOtp
                ? 'Verify Your Email'
                : isLogin
                ? 'Welcome Back'
                : 'Create Swan Drive Account'}
            </Typography>
            <Typography
              variant="body2"
              sx={{
                color: theme.palette.text.secondary,
                mt: 0.8,
                textAlign: 'center',
                fontSize: '0.875rem',
              }}
            >
              {isVerifyingOtp ? (
                <>
                  We sent a 6-digit code to <strong>{email}</strong>. Enter it below to activate your account.
                </>
              ) : isLogin ? (
                'Sign in to access Swan Drive and Swan AI'
              ) : (
                'Register your email to begin hosting private documents'
              )}
            </Typography>
          </Box>

          {/* Feedback Banners */}
          {error && (
            <Alert
              severity="error"
              sx={{
                mb: 3,
                borderRadius: '8px',
                border: '1px solid #FECACA',
                backgroundColor: isDark ? 'rgba(239, 68, 68, 0.12)' : '#FEF2F2',
                color: isDark ? '#FCA5A5' : '#991B1B',
              }}
            >
              {error}
            </Alert>
          )}

          {successMsg && (
            <Alert
              severity="success"
              sx={{
                mb: 3,
                borderRadius: '8px',
                border: '1px solid #BBF7D0',
                backgroundColor: isDark ? 'rgba(34, 197, 94, 0.12)' : '#F0FDF4',
                color: isDark ? '#86EFAC' : '#166534',
              }}
            >
              {successMsg}
            </Alert>
          )}

          {/* Form */}
          <Box component="form" onSubmit={handleSubmit} noValidate>
            {isVerifyingOtp ? (
              /* OTP Verification Step */
              <Box>
                <TextField
                  margin="normal"
                  required
                  fullWidth
                  id="otp"
                  label="Verification Code"
                  name="otp"
                  autoFocus
                  value={otp}
                  onChange={(e) => {
                    const clean = e.target.value.replace(/\D/g, '').slice(0, 6)
                    setOtp(clean)
                    setError(null)
                  }}
                  disabled={loading}
                  placeholder="••••••"
                  slotProps={{
                    htmlInput: {
                      maxLength: 6,
                      style: {
                        textAlign: 'center',
                        letterSpacing: '10px',
                        fontSize: '1.75rem',
                        fontWeight: 700,
                      },
                    },
                  }}
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: '8px',
                      backgroundColor: isDark ? '#161922' : '#FBFBFC',
                      '& fieldset': { borderColor: theme.palette.divider },
                      '&:hover fieldset': { borderColor: '#FF6B00' },
                      '&.Mui-focused fieldset': { borderColor: '#FF6B00' },
                    },
                  }}
                />

                <Button
                  type="submit"
                  fullWidth
                  variant="contained"
                  disabled={loading || otp.length !== 6}
                  sx={{
                    mt: 3,
                    mb: 2,
                    py: 1.3,
                    borderRadius: '8px',
                    backgroundColor: '#0284C7', // Water Blue
                    color: '#FFFFFF',
                    fontWeight: 700,
                    fontSize: '0.95rem',
                    '&:hover': {
                      backgroundColor: '#0369A1',
                    },
                  }}
                >
                  {loading ? (
                    <CircularProgress size={22} sx={{ color: '#FFFFFF' }} />
                  ) : (
                    'Verify & Sign In'
                  )}
                </Button>

                <Stack direction="row" spacing={1} justifyContent="center" alignItems="center" sx={{ mt: 1.5 }}>
                  <Button
                    variant="text"
                    onClick={handleResendOtp}
                    disabled={cooldownSeconds > 0 || resendLoading || loading}
                    size="small"
                    sx={{
                      color: cooldownSeconds > 0 ? theme.palette.text.disabled : '#FF6B00',
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      '&:hover': {
                        backgroundColor: 'transparent',
                        color: cooldownSeconds > 0 ? theme.palette.text.disabled : '#E05D00',
                      },
                    }}
                  >
                    {resendLoading ? (
                      <CircularProgress size={16} sx={{ mr: 1, color: '#FF6B00' }} />
                    ) : null}
                    {cooldownSeconds > 0 ? `Resend Code in ${cooldownSeconds}s` : 'Resend Code'}
                  </Button>
                  <Typography variant="body2" sx={{ color: theme.palette.divider }}>
                    &bull;
                  </Typography>
                  <Button
                    variant="text"
                    onClick={handleBackToRegister}
                    disabled={loading}
                    size="small"
                    sx={{
                      color: theme.palette.text.secondary,
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      '&:hover': {
                        backgroundColor: 'transparent',
                        color: theme.palette.text.primary,
                      },
                    }}
                  >
                    Change Email
                  </Button>
                </Stack>
              </Box>
            ) : (
              /* Standard Login & Registration Step */
              <Box>
                <TextField
                  margin="normal"
                  required
                  fullWidth
                  id="email"
                  label="Email Address"
                  name="email"
                  autoComplete="email"
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: '8px',
                      backgroundColor: isDark ? '#161922' : '#FBFBFC',
                      '& fieldset': { borderColor: theme.palette.divider },
                      '&:hover fieldset': { borderColor: '#FF6B00' },
                      '&.Mui-focused fieldset': { borderColor: '#FF6B00' },
                    },
                  }}
                />

                <TextField
                  margin="normal"
                  required
                  fullWidth
                  name="password"
                  label="Password"
                  type={showPassword ? 'text' : 'password'}
                  id="password"
                  autoComplete={isLogin ? 'current-password' : 'new-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  helperText={
                    !isLogin
                      ? 'Min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 symbol'
                      : ''
                  }
                  slotProps={{
                    input: {
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton
                            aria-label="toggle password visibility"
                            onClick={() => setShowPassword(!showPassword)}
                            edge="end"
                            size="small"
                            sx={{ color: theme.palette.text.secondary }}
                          >
                            {showPassword ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                          </IconButton>
                        </InputAdornment>
                      ),
                    },
                  }}
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: '8px',
                      backgroundColor: isDark ? '#161922' : '#FBFBFC',
                      '& fieldset': { borderColor: theme.palette.divider },
                      '&:hover fieldset': { borderColor: '#FF6B00' },
                      '&.Mui-focused fieldset': { borderColor: '#FF6B00' },
                    },
                  }}
                />

                {!isLogin && (
                  <TextField
                    margin="normal"
                    required
                    fullWidth
                    name="confirmPassword"
                    label="Confirm Password"
                    type={showPassword ? 'text' : 'password'}
                    id="confirmPassword"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    disabled={loading}
                    sx={{
                      '& .MuiOutlinedInput-root': {
                        borderRadius: '8px',
                        backgroundColor: isDark ? '#161922' : '#FBFBFC',
                        '& fieldset': { borderColor: theme.palette.divider },
                        '&:hover fieldset': { borderColor: '#FF6B00' },
                        '&.Mui-focused fieldset': { borderColor: '#FF6B00' },
                      },
                    }}
                  />
                )}

                {/* Primary Action Button (Water Blue) */}
                <Button
                  type="submit"
                  fullWidth
                  variant="contained"
                  disabled={loading}
                  sx={{
                    mt: 3,
                    mb: 2,
                    py: 1.3,
                    borderRadius: '8px',
                    backgroundColor: '#0284C7', // Water Blue
                    color: '#FFFFFF',
                    fontWeight: 700,
                    fontSize: '0.95rem',
                    '&:hover': {
                      backgroundColor: '#0369A1',
                    },
                  }}
                >
                  {loading ? (
                    <CircularProgress size={22} sx={{ color: '#FFFFFF' }} />
                  ) : isLogin ? (
                    'Sign In'
                  ) : (
                    'Create Account'
                  )}
                </Button>

                {/* Toggle Mode Option */}
                <Box sx={{ textAlign: 'center', mt: 1 }}>
                  <Button
                    variant="text"
                    onClick={toggleAuthMode}
                    disabled={loading}
                    sx={{
                      color: theme.palette.text.secondary,
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      '&:hover': {
                        backgroundColor: 'transparent',
                        color: '#FF6B00',
                      },
                    }}
                  >
                    {isLogin
                      ? "Don't have an account? Sign Up"
                      : 'Already have an account? Sign In'}
                  </Button>
                </Box>
              </Box>
            )}
          </Box>
        </CardContent>
      </Card>
    </Container>
  )
}
