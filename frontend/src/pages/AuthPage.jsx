import React, { useState } from 'react'
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
import { loginUser, registerUser } from '../apis/authApi'
import { SwanLogo } from './LandingPage'

export default function AuthPage({ onLoginSuccess, onBackToLanding, initialMode = 'login' }) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const [isLogin, setIsLogin] = useState(initialMode !== 'register')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [registerSuccess, setRegisterSuccess] = useState(false)

  const toggleAuthMode = () => {
    setIsLogin(!isLogin)
    setError(null)
    setRegisterSuccess(false)
    setPassword('')
    setConfirmPassword('')
  }

  const validateEmail = (input) => {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return re.test(input)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setRegisterSuccess(false)

    // Client-side validations
    if (!email.trim() || !password) {
      setError('Please fill in all required fields.')
      return
    }

    if (!validateEmail(email)) {
      setError('Please enter a valid email address.')
      return
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters long.')
      return
    }

    if (!isLogin && password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      if (isLogin) {
        // Authenticate User
        const response = await loginUser(email, password)
        if (response && response.access_token) {
          onLoginSuccess(response.access_token, email)
        } else {
          throw new Error('Invalid authentication response from server.')
        }
      } else {
        // Register User
        await registerUser(email, password, confirmPassword)
        setRegisterSuccess(true)
        setIsLogin(true)
        setPassword('')
        setConfirmPassword('')
      }
    } catch (err) {
      console.error(err)
      setError(err.message || 'Authentication request failed. Please check credentials.')
    } finally {
      setLoading(false)
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
              <SwanLogo size={38} />
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
              {isLogin ? 'Welcome Back' : 'Create Swan Drive Account'}
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
              {isLogin
                ? 'Sign in to access your cloud vault and knowledge base'
                : 'Register your email to begin hosting private documents'}
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

          {registerSuccess && (
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
              Account created successfully! Please sign in now.
            </Alert>
          )}

          {/* Form */}
          <Box component="form" onSubmit={handleSubmit} noValidate>
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
        </CardContent>
      </Card>
    </Container>
  )
}
