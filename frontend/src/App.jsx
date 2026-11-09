import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  ThemeProvider,
  CssBaseline,
  Container,
  Box,
  Typography,
} from '@mui/material'
import { Analytics } from '@vercel/analytics/react'
import { pingSystem } from './apis/systemApi'

import Header from './components/Header'
import Sidebar from './components/Sidebar'
import LandingPage from './pages/LandingPage'
import AuthPage from './pages/AuthPage'
import VaultPage from './pages/VaultPage'
import KnowledgeBase from './pages/KnowledgeBase'
import { KnowledgeBaseFilesProvider } from './context/KnowledgeBaseFilesContext'
import { createAppTheme } from './theme'

import {
  getToken,
  clearToken,
  decodeToken,
  saveToken,
  isAuthenticated,
} from './services/authService'

/**
 * frontend/src/App.jsx
 *
 * Swan Drive — AI Cloud Storage Platform
 * Frontend UI/UX Redesign Root.
 */

function App() {
  // Theme Mode State (Light / Dark)
  const [themeMode, setThemeMode] = useState(() => {
    return localStorage.getItem('swan_drive_theme') || 'light'
  })

  const handleToggleTheme = useCallback(() => {
    setThemeMode((prev) => {
      const next = prev === 'light' ? 'dark' : 'light'
      localStorage.setItem('swan_drive_theme', next)
      return next
    })
  }, [])

  // Session States
  const [token, setToken] = useState(() => getToken())
  const [currentUser, setCurrentUser] = useState(() => {
    const activeToken = getToken()
    if (!activeToken || !isAuthenticated()) return null
    const decoded = decodeToken(activeToken)
    const rawEmail = localStorage.getItem('pkb_user_email')
    // Clean up a poisoned literal "undefined" left by the old bug path.
    if (rawEmail === 'undefined' || rawEmail === 'null') {
      localStorage.removeItem('pkb_user_email')
    }
    const storedEmail = rawEmail && rawEmail !== 'undefined' && rawEmail !== 'null' ? rawEmail : null
    const tokenEmail = decoded?.email || null
    const email = tokenEmail || storedEmail || null
    // Persist token email to localStorage for older tokens that didn't carry it
    if (tokenEmail && tokenEmail !== storedEmail) {
      localStorage.setItem('pkb_user_email', tokenEmail)
    }
    return { id: decoded?.sub, email }
  })

  // Unauthenticated view state: 'landing' | 'login' | 'register'
  const [authView, setAuthView] = useState('landing')

  // App frame state
  const [backendStatus, setBackendStatus] = useState('checking')
  const [view, setView] = useState('vault')
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev)
  }, [])

  // Check backend connectivity once on mount (feeds the Header status dot).
  useEffect(() => {
    const checkConnection = async () => {
      try {
        await pingSystem()
        setBackendStatus('online')
      } catch (err) {
        console.error('Backend connection check failed:', err)
        setBackendStatus('offline')
      }
    }
    checkConnection()
  }, [])

  // Login handler
  const handleLoginSuccess = useCallback((accessToken, userEmail) => {
    saveToken(accessToken)
    const decoded = decodeToken(accessToken)
    const tokenEmail = decoded?.email || null
    const safeEmail = userEmail && userEmail !== 'undefined' && userEmail !== 'null' ? String(userEmail) : null
    const finalEmail = tokenEmail || safeEmail || null
    if (finalEmail) localStorage.setItem('pkb_user_email', finalEmail)
    else localStorage.removeItem('pkb_user_email')
    setToken(accessToken)
    setCurrentUser({ id: decoded?.sub, email: finalEmail })
  }, [])

  // Logout handler
  const handleLogout = useCallback(() => {
    clearToken()
    localStorage.removeItem('pkb_user_email')
    setToken(null)
    setCurrentUser(null)
    setView('vault')
    setAuthView('landing')
  }, [])

  // Create Swan Drive Theme based on mode
  const theme = useMemo(() => createAppTheme(themeMode), [themeMode])

  const isUserAuthenticated = token && isAuthenticated()

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: theme.palette.background.default,
          color: theme.palette.text.primary,
        }}
      >
        {!isUserAuthenticated ? (
          authView === 'landing' ? (
            <LandingPage
              onLoginClick={() => setAuthView('login')}
              onRegisterClick={() => setAuthView('register')}
              themeMode={themeMode}
              onToggleTheme={handleToggleTheme}
            />
          ) : (
            <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
              <Header
                backendStatus={backendStatus}
                currentUser={null}
                onLogout={handleLogout}
                themeMode={themeMode}
                onToggleTheme={handleToggleTheme}
              />
              <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center' }}>
                <AuthPage
                  onLoginSuccess={handleLoginSuccess}
                  onBackToLanding={() => setAuthView('landing')}
                  initialMode={authView}
                />
              </Box>
              <Box
                component="footer"
                sx={{
                  py: 3,
                  borderTop: `1px solid ${theme.palette.divider}`,
                  backgroundColor: theme.palette.background.paper,
                  textAlign: 'center',
                  mt: 'auto',
                }}
              >
                <Container maxWidth="lg">
                  <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontWeight: 500 }}>
                    &copy; {new Date().getFullYear()} Swan Drive. Secure Cloud Storage & Intelligent AI.
                  </Typography>
                </Container>
              </Box>
            </Box>
          )
        ) : (
          <KnowledgeBaseFilesProvider userId={currentUser?.id}>
            {/* Authenticated Swan Drive Header */}
            <Header
              backendStatus={backendStatus}
              currentUser={currentUser}
              onLogout={handleLogout}
              onToggleSidebar={handleToggleSidebar}
              sidebarOpen={sidebarOpen}
              themeMode={themeMode}
              onToggleTheme={handleToggleTheme}
            />

            <Box sx={{ display: 'flex', flexGrow: 1, minHeight: 'calc(100vh - 64px)' }}>
              {/* Collapsible Left-side Navigation Sidebar */}
              <Sidebar
                open={sidebarOpen}
                onToggle={handleToggleSidebar}
                currentView={view}
                onViewChange={setView}
              />

              {/* Main Workspace Area */}
              <Box
                component="main"
                sx={{
                  flexGrow: 1,
                  minWidth: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  backgroundColor: theme.palette.background.default,
                  overflow: 'hidden',
                }}
              >
                {/* Knowledge Base View */}
                <Box
                  sx={{
                    display: view === 'knowledge' ? 'flex' : 'none',
                    flexDirection: 'column',
                    flexGrow: 1,
                    minHeight: 0,
                  }}
                >
                  <KnowledgeBase userId={currentUser?.id} />
                </Box>

                {/* Vault View */}
                <Box
                  sx={{
                    display: view === 'vault' ? 'flex' : 'none',
                    flexDirection: 'column',
                    flexGrow: 1,
                    overflowY: 'auto',
                  }}
                >
                  <Container maxWidth="lg" sx={{ mt: 4, mb: 6, flexGrow: 1 }}>
                    <VaultPage />
                  </Container>

                  {/* Vault Footer */}
                  <Box
                    component="footer"
                    sx={{
                      py: 3,
                      borderTop: `1px solid ${theme.palette.divider}`,
                      backgroundColor: theme.palette.background.paper,
                      textAlign: 'center',
                      mt: 'auto',
                    }}
                  >
                    <Container maxWidth="lg">
                      <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontWeight: 500 }}>
                        &copy; {new Date().getFullYear()} Swan Drive. Secure Cloud Storage & Intelligent AI.
                      </Typography>
                    </Container>
                  </Box>
                </Box>
              </Box>
            </Box>
          </KnowledgeBaseFilesProvider>
        )}
        <Analytics />
      </Box>
    </ThemeProvider>
  )
}

export default App
