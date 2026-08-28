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
  CircularProgress
} from '@mui/material'
import Visibility from '@mui/icons-material/Visibility'
import VisibilityOff from '@mui/icons-material/VisibilityOff'
import LockOutlinedIcon from '@mui/icons-material/LockOutlined'
import PersonAddOutlinedIcon from '@mui/icons-material/PersonAddOutlined'
import { loginUser, registerUser } from '../apis/authApi'

export default function AuthPage({ onLoginSuccess }) {
  const [isLogin, setIsLogin] = useState(true)
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
          onLoginSuccess(response.access_token)
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
    <Container maxWidth="xs" sx={{ minHeight: '85vh', display: 'flex', alignItems: 'center', justifyContent: 'center', py: 4 }}>
      <Card sx={{ width: '100%', borderRadius: '12px', border: '1px solid #E2E8F0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05)' }}>
        <CardContent sx={{ p: 4 }}>
          {/* Header Icon & Title */}
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', mb: 3 }}>
            <Box sx={{ p: 1.5, borderRadius: '50%', backgroundColor: '#F1F5F9', color: '#0A192F', display: 'flex', mb: 1 }}>
              {isLogin ? <LockOutlinedIcon /> : <PersonAddOutlinedIcon />}
            </Box>
            <Typography variant="h5" sx={{ fontWeight: 800, color: '#0F172A', fontFamily: 'Outfit' }}>
              {isLogin ? 'Welcome Back' : 'Create Account'}
            </Typography>
            <Typography variant="body2" sx={{ color: '#64748B', mt: 0.5, textAlign: 'center' }}>
              {isLogin ? 'Log in to access your cloud document vault' : 'Register email to host and search private documents'}
            </Typography>
          </Box>

          {/* Feedback Banners */}
          {error && (
            <Alert severity="error" sx={{ mb: 3, borderRadius: '8px', border: '1px solid #FECACA', backgroundColor: '#FEF2F2', color: '#991B1B' }}>
              {error}
            </Alert>
          )}

          {registerSuccess && (
            <Alert severity="success" sx={{ mb: 3, borderRadius: '8px', border: '1px solid #BBF7D0', backgroundColor: '#F0FDF4', color: '#166534' }}>
              Account created successfully! Please log in now.
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
                }
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
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label="toggle password visibility"
                      onClick={() => setShowPassword(!showPassword)}
                      edge="end"
                    >
                      {showPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
              sx={{
                '& .MuiOutlinedInput-root': {
                  borderRadius: '8px',
                }
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
                  }
                }}
              />
            )}

            <Button
              type="submit"
              fullWidth
              variant="contained"
              disabled={loading}
              sx={{
                mt: 3,
                mb: 2,
                py: 1.5,
                borderRadius: '8px',
                backgroundColor: '#0A192F',
                '&:hover': {
                  backgroundColor: '#1E293B',
                },
                fontWeight: 700
              }}
            >
              {loading ? (
                <CircularProgress size={24} sx={{ color: '#FFFFFF' }} />
              ) : isLogin ? (
                'Sign In'
              ) : (
                'Sign Up'
              )}
            </Button>

            {/* Toggle Mode Option */}
            <Box sx={{ textAlignment: 'center', mt: 1, display: 'flex', justifyContent: 'center' }}>
              <Button
                variant="text"
                onClick={toggleAuthMode}
                disabled={loading}
                sx={{
                  color: '#64748B',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  '&:hover': {
                    backgroundColor: 'transparent',
                    color: '#0A192F',
                  }
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
