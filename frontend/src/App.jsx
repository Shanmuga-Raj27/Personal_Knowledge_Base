import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  ThemeProvider,
  createTheme,
  CssBaseline,
  Container,
  Box,
  Tabs,
  Tab,
  Typography
} from '@mui/material'
import { pingSystem } from './apis/systemApi'

import Header from './components/Header'
import AuthPage from './pages/AuthPage'
import VaultPage from './pages/VaultPage'
import KnowledgeBase from './pages/KnowledgeBase'
import { KnowledgeBaseFilesProvider } from './context/KnowledgeBaseFilesContext'

import {
  getToken,
  clearToken,
  decodeToken,
  saveToken,
  isAuthenticated
} from './services/authService'

/**
 * frontend/src/App.jsx
 *
 * Phase 8 §3 Step 6 — composition root only.
 *
 * Owns the auth gate, theme, header, footer, and the MUI Tabs that switch
 * between the two authenticated views (Vault / Knowledge Base). Everything
 * page-specific lives in ./pages/VaultPage.jsx and ./pages/KnowledgeBase.jsx —
 * conditional render unmounts the hidden view, so each page reloads its data
 * (documents) on entry.
 */

function App() {
  // Session States
  const [token, setToken] = useState(() => getToken())
  const [currentUser, setCurrentUser] = useState(() => {
    const activeToken = getToken()
    const email = localStorage.getItem('pkb_user_email')
    if (activeToken && email && isAuthenticated()) {
      const decoded = decodeToken(activeToken)
      return { id: decoded?.sub, email }
    }
    return null
  })

  // App frame state
  const [backendStatus, setBackendStatus] = useState('checking')
  const [view, setView] = useState('vault')

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
    localStorage.setItem('pkb_user_email', userEmail)
    const decoded = decodeToken(accessToken)
    setToken(accessToken)
    setCurrentUser({ id: decoded?.sub, email: userEmail })
  }, [])

  // Logout handler
  const handleLogout = useCallback(() => {
    clearToken()
    localStorage.removeItem('pkb_user_email')
    setToken(null)
    setCurrentUser(null)
    setView('vault')
  }, [])

  // Tab switch handler
  const handleViewChange = useCallback((_e, v) => {
    setView(v)
  }, [])

  // Tokenized Light Theme Design System
  const theme = useMemo(
    () =>
      createTheme({
        palette: {
          mode: 'light',
          primary: {
            main: '#0A192F'
          },
          background: {
            default: '#F8FAFC',
            paper: '#FFFFFF'
          },
          text: {
            primary: '#0F172A',
            secondary: '#64748B'
          },
          divider: '#E2E8F0'
        },
        typography: {
          fontFamily: `'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`,
          button: {
            textTransform: 'none',
            fontWeight: 700
          }
        },
        components: {
          MuiPaper: {
            styleOverrides: {
              root: {
                backgroundImage: 'none',
                boxShadow: 'none'
              }
            }
          }
        }
      }),
    []
  )

  const isUserAuthenticated = token && isAuthenticated()

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#F8FAFC' }}>
        {/* Minimal Header */}
        <Header
          backendStatus={backendStatus}
          currentUser={currentUser}
          onLogout={handleLogout}
        />

        {/* Conditional views depending on session */}
        {!isUserAuthenticated ? (
          <AuthPage onLoginSuccess={handleLoginSuccess} />
        ) : (
          <Container maxWidth="lg" sx={{ mt: 5, mb: 6, flexGrow: 1 }}>
            {/* View switcher: Vault <-> Knowledge Base */}
            <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
              <Tabs
                value={view}
                onChange={handleViewChange}
                textColor="primary"
                indicatorColor="primary"
                sx={{
                  '& .MuiTab-root': {
                    textTransform: 'none',
                    fontWeight: 700,
                    fontSize: '0.9rem'
                  }
                }}
              >
                <Tab label="Vault" value="vault" />
                <Tab label="Knowledge Base" value="knowledge" />
              </Tabs>
            </Box>

            {/* Shared KB selection lives above both pages so Vault can add
                to it and the Knowledge Base page sees it immediately.
                Each page itself is keep-mounted for scroll/chat state. */}
            <KnowledgeBaseFilesProvider userId={currentUser?.id}>
              <Box sx={{ display: view === 'knowledge' ? 'block' : 'none' }}>
                <KnowledgeBase userId={currentUser?.id} />
              </Box>
              <Box sx={{ display: view === 'vault' ? 'block' : 'none' }}>
                <VaultPage />
              </Box>
            </KnowledgeBaseFilesProvider>
          </Container>
        )}

        {/* Footer */}
        <Box
          component="footer"
          sx={{
            py: 3,
            borderTop: '1px solid #E2E8F0',
            backgroundColor: '#FFFFFF',
            textAlign: 'center'
          }}
        >
          <Container maxWidth="lg">
            <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 500 }}>
              &copy; {new Date().getFullYear()} Personal Knowledge Base. Minimalist Cloud Document Vault.
            </Typography>
          </Container>
        </Box>
      </Box>
    </ThemeProvider>
  )
}

export default App