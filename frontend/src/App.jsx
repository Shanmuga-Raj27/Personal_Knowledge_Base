import React, { useState, useEffect, useMemo } from 'react'
import {
  ThemeProvider,
  createTheme,
  CssBaseline,
  AppBar,
  Toolbar,
  Typography,
  Container,
  Box,
  Button,
  Grid,
  Paper,
  LinearProgress,
  IconButton
} from '@mui/material'
import { pingSystem } from './apis/systemApi'
import { getUploadUrl, completeUpload, getViewUrl } from './apis/documentApi'

// File validation mapping
const ALLOWED_EXTENSIONS = {
  'text/plain': '.txt',
  'text/markdown': '.md',
  'application/pdf': '.pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx'
}

// Inline custom SVG icons for high-contrast minimalism without dependency issues
const SunIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2" />
    <path d="M12 20v2" />
    <path d="m4.93 4.93 1.41 1.41" />
    <path d="m17.66 17.66 1.41 1.41" />
    <path d="M2 12h2" />
    <path d="M20 12h2" />
    <path d="m6.34 17.66-1.41 1.41" />
    <path d="m19.07 4.93-1.41 1.41" />
  </svg>
)

const MoonIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
  </svg>
)

const UploadIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
)

const FileIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
    <path d="M14 2v4a2 2 0 0 0 2 2h4" />
    <path d="M10 9H8" />
    <path d="M16 13H8" />
    <path d="M16 17H8" />
  </svg>
)

const CheckIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

const AlertIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
)

const LockIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
)

const CloseIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
)

const EyeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

function App() {
  // Theme state persisted in localStorage
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('darkMode')
    if (saved !== null) return saved === 'true'
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  // Synchronize darkMode to localStorage
  useEffect(() => {
    localStorage.setItem('darkMode', darkMode)
  }, [darkMode])

  // System States
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [viewLoading, setViewLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [lastUploadedKey, setLastUploadedKey] = useState(null)
  const [backendStatus, setBackendStatus] = useState('checking')

  // Check backend connectivity on mount
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

  // Handle selected file validation
  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0]
    setError(null)
    setSuccess(null)
    
    if (!selectedFile) {
      setFile(null)
      return
    }

    if (!(selectedFile.type in ALLOWED_EXTENSIONS)) {
      setError(`Unsupported file type (${selectedFile.type || 'unknown'}). Please upload a .txt, .md, .pdf, or .docx file.`)
      setFile(null)
      return
    }

    setFile(selectedFile)
  }

  // Handle document upload directly to S3 storage via presigned URL with two-step verification
  const handleUpload = async () => {
    if (!file) return

    setUploading(true)
    setVerifying(false)
    setProgress(0)
    setError(null)
    setSuccess(null)

    try {
      // Step 1: Request presigned PUT URL
      const { uploadUrl, key } = await getUploadUrl(file.name, file.type)

      // Step 2: Upload file directly using XMLHttpRequest to track progress
      await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('PUT', uploadUrl, true)
        xhr.setRequestHeader('Content-Type', file.type)

        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const percent = Math.round((event.loaded / event.total) * 100)
            setProgress(percent)
          }
        }

        xhr.onload = () => {
          if (xhr.status === 200) {
            resolve()
          } else {
            reject(new Error(`Storage upload failed with status ${xhr.status}`))
          }
        }

        xhr.onerror = () => {
          reject(new Error('Network error during upload.'))
        }

        xhr.send(file)
      })

      // Step 3: Two-step handshake verification with backend
      setVerifying(true)
      const verifyRes = await completeUpload(key, file.name)

      if (verifyRes.verified) {
        setSuccess({
          message: 'Document uploaded and verified in cloud storage.',
          key: key,
        })
        setLastUploadedKey(key)
        setFile(null)
      } else {
        throw new Error('Upload verification failed. File not found in storage.')
      }
    } catch (err) {
      console.error(err)
      setError(err.message || 'An error occurred during upload.')
    } finally {
      setUploading(false)
      setVerifying(false)
    }
  }

  // Handle requesting presigned GET URL to view or read the file
  const handleViewFile = async (keyToView) => {
    const targetKey = keyToView || lastUploadedKey
    if (!targetKey) return

    setViewLoading(true)
    setError(null)
    try {
      const { viewUrl } = await getViewUrl(targetKey)
      if (viewUrl) {
        window.open(viewUrl, '_blank')
      }
    } catch (err) {
      console.error(err)
      setError(err.message || 'Failed to generate view URL.')
    } finally {
      setViewLoading(false)
    }
  }

  // Build minimalist high contrast theme dynamically (with Slate Gray/Coal color background)
  const theme = useMemo(() => createTheme({
    palette: {
      mode: darkMode ? 'dark' : 'light',
      primary: {
        main: darkMode ? '#ffffff' : '#000000',
      },
      background: {
        default: darkMode ? '#121214' : '#f4f4f7', // Coal background / Light gray background
        paper: darkMode ? '#18181c' : '#ffffff',   // Paper background
      },
      text: {
        primary: darkMode ? '#ffffff' : '#000000',
        secondary: darkMode ? '#a1a1aa' : '#5c5c64',
      },
      divider: darkMode ? '#2c2c35' : '#d2d2d7',
    },
    typography: {
      fontFamily: `'Outfit', sans-serif`,
      h4: {
        fontWeight: 700,
        letterSpacing: '-0.03em',
      },
      h6: {
        fontWeight: 600,
        letterSpacing: '-0.01em',
      },
      subtitle1: {
        letterSpacing: '-0.01em',
      },
      button: {
        textTransform: 'none',
        fontWeight: 600,
        letterSpacing: '0.01em',
      },
    },
    components: {
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: '6px',
            padding: '10px 24px',
            boxShadow: 'none',
            '&:hover': {
              boxShadow: 'none',
            },
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
            boxShadow: 'none',
          },
        },
      },
    },
  }), [darkMode])

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', transition: 'background-color 0.2s ease, color 0.2s ease' }}>
        
        {/* Navigation Bar */}
        <AppBar position="static" color="transparent" sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
          <Container maxWidth="lg">
            <Toolbar disableGutters sx={{ height: 72, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Typography sx={{ fontWeight: 700, fontSize: '1.2rem', letterSpacing: '-0.03em', color: 'text.primary', cursor: 'default' }}>
                  Personal Knowledge Base
                </Typography>
                
                {/* Minimalist Connection Dot Indicator */}
                <Box sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  px: 1.5,
                  py: 0.5,
                  borderRadius: '16px',
                  border: '1px solid',
                  borderColor: 'divider',
                  backgroundColor: darkMode ? '#1c1c22' : '#e4e4eb'
                }}>
                  <Box sx={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    backgroundColor: backendStatus === 'online' ? '#52c41a' : backendStatus === 'offline' ? '#ff4d4f' : '#faad14',
                    animation: backendStatus === 'checking' ? 'pulse 1.5s infinite' : 'none',
                    '@keyframes pulse': {
                      '0%': { transform: 'scale(0.8)', opacity: 0.5 },
                      '50%': { transform: 'scale(1.2)', opacity: 1 },
                      '100%': { transform: 'scale(0.8)', opacity: 0.5 },
                    }
                  }} />
                  <Typography sx={{ fontSize: '0.72rem', fontWeight: 600, color: 'text.secondary', textTransform: 'uppercase', letterSpacing: '0.02em' }}>
                    {backendStatus === 'online' ? 'Online' : backendStatus === 'offline' ? 'Offline' : 'Connecting'}
                  </Typography>
                </Box>
              </Box>

              {/* Theme Toggle Switcher */}
              <IconButton 
                onClick={() => setDarkMode(!darkMode)} 
                color="inherit" 
                sx={{ 
                  p: 1.2, 
                  border: '1px solid', 
                  borderColor: 'divider', 
                  borderRadius: '6px',
                  backgroundColor: darkMode ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.02)',
                  transition: 'all 0.2s',
                  '&:hover': {
                    borderColor: 'text.primary',
                    backgroundColor: darkMode ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.05)',
                  }
                }}
              >
                {darkMode ? <SunIcon /> : <MoonIcon />}
              </IconButton>
            </Toolbar>
          </Container>
        </AppBar>

        {/* Content Section */}
        <Container maxWidth="lg" sx={{ mt: { xs: 6, md: 10 }, mb: 6, flexGrow: 1 }}>
          <Grid container spacing={{ xs: 4, md: 8 }} sx={{ alignItems: 'center' }}>
            
            {/* Left Column: Product Information */}
            <Grid xs={12} md={6}>
              <Box sx={{ pr: { md: 4 } }}>
                <Typography variant="overline" sx={{ letterSpacing: '0.15em', fontWeight: 700, color: 'text.secondary', display: 'block', mb: 2 }}>
                  Secure Document Vault
                </Typography>
                <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 800, color: 'text.primary', mb: 3, lineHeight: 1.25 }}>
                  Simplify your data storage.
                </Typography>
                <Typography variant="subtitle1" color="text.secondary" sx={{ mb: 4, lineHeight: 1.6 }}>
                  A secure, clean space for text files, Markdown, PDF documents, and Microsoft Word files. Connect directly to S3-compatible cloud storage with temporary security parameters.
                </Typography>

                {/* Key Features Indicators - Redesigned with custom colors for minimalism */}
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', flexDirection: 'column', gap: 1.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box sx={{ color: 'text.primary', display: 'flex', alignItems: 'center' }}>
                        <FileIcon />
                      </Box>
                      <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.primary' }}>
                        Supported file formats:
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', pl: 3.5 }}>
                      {/* High-contrast multi-color minimalist pills */}
                      <Box sx={{ px: 1.5, py: 0.5, borderRadius: '4px', border: '1px solid', borderColor: '#ff4d4f', color: '#ff4d4f', backgroundColor: darkMode ? 'rgba(255, 77, 79, 0.08)' : 'rgba(255, 77, 79, 0.03)', fontSize: '0.75rem', fontWeight: 700 }}>
                        PDF
                      </Box>
                      <Box sx={{ px: 1.5, py: 0.5, borderRadius: '4px', border: '1px solid', borderColor: '#1890ff', color: '#1890ff', backgroundColor: darkMode ? 'rgba(24, 144, 255, 0.08)' : 'rgba(24, 144, 255, 0.03)', fontSize: '0.75rem', fontWeight: 700 }}>
                        MARKDOWN
                      </Box>
                      <Box sx={{ px: 1.5, py: 0.5, borderRadius: '4px', border: '1px solid', borderColor: '#52c41a', color: '#52c41a', backgroundColor: darkMode ? 'rgba(82, 196, 26, 0.08)' : 'rgba(82, 196, 26, 0.03)', fontSize: '0.75rem', fontWeight: 700 }}>
                        TXT
                      </Box>
                      <Box sx={{ px: 1.5, py: 0.5, borderRadius: '4px', border: '1px solid', borderColor: '#722ed1', color: '#722ed1', backgroundColor: darkMode ? 'rgba(114, 46, 209, 0.08)' : 'rgba(114, 46, 209, 0.03)', fontSize: '0.75rem', fontWeight: 700 }}>
                        DOCX
                      </Box>
                    </Box>
                  </Box>
                  
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Box sx={{ color: 'text.primary', display: 'flex', alignItems: 'center' }}>
                      <LockIcon />
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 500 }}>
                      Direct client-side uploads block server leaks
                    </Typography>
                  </Box>
                </Box>
              </Box>
            </Grid>

            {/* Right Column: Upload Component */}
            <Grid xs={12} md={6}>
              <Paper 
                variant="outlined" 
                sx={{ 
                  border: '1px solid', 
                  borderColor: 'divider', 
                  borderRadius: '8px', 
                  backgroundColor: 'background.paper',
                  display: 'flex',
                  flexDirection: 'column',
                  overflow: 'hidden'
                }}
              >
                {/* Modern high-contrast color bar at top matching the file pills */}
                <Box sx={{
                  height: 4,
                  background: 'linear-gradient(90deg, #ff4d4f 0%, #1890ff 33%, #52c41a 66%, #722ed1 100%)',
                }} />

                <Box sx={{ p: 4, display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <div>
                    <Typography variant="h6" sx={{ color: 'text.primary', mb: 1 }}>
                      Document Upload
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Select a document to securely transfer it to storage.
                    </Typography>
                  </div>

                  {/* Drag and Drop Zone Area */}
                  <Box
                    component="label"
                    sx={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      p: 4,
                      border: '1px dashed',
                      borderColor: file ? 'text.primary' : 'divider',
                      borderRadius: '6px',
                      backgroundColor: darkMode ? 'rgba(255, 255, 255, 0.01)' : 'rgba(0, 0, 0, 0.005)',
                      cursor: uploading ? 'not-allowed' : 'pointer',
                      transition: 'all 0.2s ease',
                      '&:hover': {
                        borderColor: uploading ? 'divider' : 'text.primary',
                        backgroundColor: uploading ? 'transparent' : (darkMode ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.02)'),
                      }
                    }}
                  >
                    <input
                      type="file"
                      hidden
                      onChange={handleFileChange}
                      accept=".txt,.md,.pdf,.docx"
                      disabled={uploading}
                    />
                    <Box sx={{ color: 'text.secondary', mb: 2, display: 'flex', alignItems: 'center' }}>
                      <UploadIcon />
                    </Box>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.primary', mb: 0.5 }}>
                      Click to select file
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Allowed formats: PDF, Markdown, TXT, DOCX
                    </Typography>
                  </Box>

                  {/* Selected File Details & Clear Action */}
                  {file && (
                    <Box sx={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'space-between', 
                      p: 2, 
                      border: '1px solid', 
                      borderColor: 'divider', 
                      borderRadius: '6px', 
                      backgroundColor: darkMode ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 0, 0, 0.01)' 
                    }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, overflow: 'hidden' }}>
                        <Box sx={{ color: 'text.primary', display: 'flex', alignItems: 'center' }}>
                          <FileIcon />
                        </Box>
                        <Box sx={{ overflow: 'hidden' }}>
                          <Typography sx={{ fontSize: '0.85rem', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {file.name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {(file.size / 1024).toFixed(1)} KB
                          </Typography>
                        </Box>
                      </Box>
                      <IconButton size="small" onClick={() => setFile(null)} disabled={uploading} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: '4px' }}>
                        <CloseIcon />
                      </IconButton>
                    </Box>
                  )}

                  {/* Error Banner */}
                  {error && (
                    <Box sx={{ 
                      display: 'flex', 
                      alignItems: 'flex-start', 
                      gap: 1.5, 
                      p: 2, 
                      border: '1px solid', 
                      borderColor: '#ff4d4f', 
                      borderRadius: '6px', 
                      backgroundColor: darkMode ? 'rgba(255, 77, 79, 0.08)' : 'rgba(255, 77, 79, 0.04)' 
                    }}>
                      <Box sx={{ color: '#ff4d4f', mt: 0.2 }}>
                        <AlertIcon />
                      </Box>
                      <Typography sx={{ fontSize: '0.85rem', color: '#ff4d4f', fontWeight: 500 }}>
                        {error}
                      </Typography>
                    </Box>
                  )}

                  {/* Success Banner & View Action */}
                  {success && (
                    <Box sx={{ 
                      display: 'flex', 
                      flexDirection: 'column',
                      gap: 1.5, 
                      p: 2, 
                      border: '1px solid', 
                      borderColor: '#52c41a', 
                      borderRadius: '6px', 
                      backgroundColor: darkMode ? 'rgba(82, 196, 26, 0.08)' : 'rgba(82, 196, 26, 0.04)' 
                    }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                        <Box sx={{ color: '#52c41a', display: 'flex', alignItems: 'center' }}>
                          <CheckIcon />
                        </Box>
                        <Typography sx={{ fontSize: '0.85rem', color: '#52c41a', fontWeight: 600, flexGrow: 1 }}>
                          {success.message}
                        </Typography>
                      </Box>
                      
                      {success.key && (
                        <Button
                          variant="outlined"
                          size="small"
                          disabled={viewLoading}
                          onClick={() => handleViewFile(success.key)}
                          startIcon={<EyeIcon />}
                          sx={{
                            alignSelf: 'flex-start',
                            borderColor: '#52c41a',
                            color: darkMode ? '#ffffff' : '#141414',
                            fontSize: '0.78rem',
                            py: 0.6,
                            px: 1.5,
                            '&:hover': {
                              borderColor: '#52c41a',
                              backgroundColor: darkMode ? 'rgba(82, 196, 26, 0.15)' : 'rgba(82, 196, 26, 0.1)',
                            }
                          }}
                        >
                          {viewLoading ? 'Opening File...' : 'View / Read File'}
                        </Button>
                      )}
                    </Box>
                  )}

                  {/* Upload Progress Indicator */}
                  {uploading && (
                    <Box sx={{ width: '100%' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.primary' }}>
                          {verifying ? 'Verifying S3 storage...' : 'Uploading...'}
                        </Typography>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.primary' }}>
                          {progress}%
                        </Typography>
                      </Box>
                      <LinearProgress 
                        variant="determinate" 
                        value={progress} 
                        sx={{ 
                          height: 6, 
                          borderRadius: 3, 
                          backgroundColor: darkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
                          '& .MuiLinearProgress-bar': {
                            background: 'linear-gradient(90deg, #1890ff 0%, #52c41a 100%)'
                          }
                        }} 
                      />
                    </Box>
                  )}

                  {/* Submit Action Button */}
                  <Button
                    variant="contained"
                    disabled={!file || uploading}
                    onClick={handleUpload}
                    sx={{
                      py: 1.5,
                      backgroundColor: 'text.primary',
                      color: 'background.default',
                      border: '1px solid transparent',
                      '&:hover': {
                        backgroundColor: 'background.default',
                        color: 'text.primary',
                        borderColor: 'text.primary',
                      },
                      '&.Mui-disabled': {
                        backgroundColor: darkMode ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)',
                        color: 'text.secondary',
                        borderColor: 'divider'
                      }
                    }}
                  >
                    {uploading ? (verifying ? 'Verifying Upload...' : 'Transferring...') : 'Upload Document'}
                  </Button>
                </Box>
              </Paper>
            </Grid>

          </Grid>
        </Container>

        {/* Minimal Footer */}
        <Box 
          component="footer" 
          sx={{ 
            py: 4, 
            borderTop: '1px solid', 
            borderColor: 'divider', 
            backgroundColor: 'background.default', 
            textAlign: 'center',
            transition: 'all 0.2s'
          }}
        >
          <Container maxWidth="lg">
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>
              &copy; {new Date().getFullYear()} Personal Knowledge Base. All rights reserved.
            </Typography>
          </Container>
        </Box>

      </Box>
    </ThemeProvider>
  )
}

export default App
