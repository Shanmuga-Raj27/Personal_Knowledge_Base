import React, { useState, useEffect } from 'react'
import {
  AppBar,
  Toolbar,
  Typography,
  Container,
  Box,
  Button,
  Grid,
  Card,
  CardContent,
  LinearProgress,
  Alert,
  Paper,
  Divider,
  List,
  ListItem,
  ListItemText,
} from '@mui/material'
import { pingSystem } from './apis/systemApi'
import { getUploadUrl } from './apis/documentApi'

const ALLOWED_EXTENSIONS = {
  'text/plain': '.txt',
  'text/markdown': '.md',
  'application/pdf': '.pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx'
}

function App() {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [backendStatus, setBackendStatus] = useState('checking')

  // Check backend connectivity on component mount
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

  const handleUpload = async () => {
    if (!file) return

    setUploading(true)
    setProgress(0)
    setError(null)
    setSuccess(null)

    try {
      // Step 1: Request presigned PUT URL from FastAPI backend via centralized Axios client
      const { uploadUrl, key } = await getUploadUrl(file.name, file.type)

      // Step 2: Upload file directly to Backblaze B2 S3 using the presigned URL
      // Since fetch doesn't natively have progress events, we will simulate progress steps or use XMLHttpRequest
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
            reject(new Error(`Storage provider upload failed with status ${xhr.status}`))
          }
        }

        xhr.onerror = () => {
          reject(new Error('Network error during upload to storage provider.'))
        }

        xhr.send(file)
      })

      setSuccess({
        message: 'File successfully uploaded directly to Backblaze B2!',
        key: key,
        filename: file.name,
      })
      setFile(null)
    } catch (err) {
      console.error(err)
      setError(err.message || 'An unexpected error occurred during upload.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <Box sx={{ flexGrow: 1, minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Navbar */}
      <AppBar position="static" color="default" elevation={1} sx={{ backgroundColor: 'background.paper' }}>
        <Toolbar>
          <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="h6" component="div" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
              PKB // Personal Knowledge Base
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  backgroundColor:
                    backendStatus === 'online'
                      ? 'success.main'
                      : backendStatus === 'offline'
                      ? 'error.main'
                      : 'warning.main',
                  mr: 1,
                  boxShadow:
                    backendStatus === 'online'
                      ? '0 0 8px rgba(46, 125, 50, 0.5)'
                      : backendStatus === 'offline'
                      ? '0 0 8px rgba(211, 47, 47, 0.5)'
                      : '0 0 8px rgba(237, 108, 2, 0.5)',
                  animation: backendStatus === 'checking' ? 'pulse 1.5s infinite' : 'none',
                  '@keyframes pulse': {
                    '0%': { transform: 'scale(0.8)', opacity: 0.5 },
                    '50%': { transform: 'scale(1.2)', opacity: 1 },
                    '100%': { transform: 'scale(0.8)', opacity: 0.5 },
                  },
                }}
              />
              <Typography
                variant="caption"
                sx={{
                  color:
                    backendStatus === 'online'
                      ? 'success.main'
                      : backendStatus === 'offline'
                      ? 'error.main'
                      : 'warning.main',
                  fontWeight: 'bold',
                  textTransform: 'uppercase',
                  fontSize: '0.7rem',
                  letterSpacing: 0.5,
                }}
              >
                {backendStatus === 'online'
                  ? 'Online'
                  : backendStatus === 'offline'
                  ? 'Offline'
                  : 'Connecting'}
              </Typography>
            </Box>
          </Box>
          <Button color="primary" href="https://github.com" target="_blank">
            GitHub
          </Button>
        </Toolbar>
      </AppBar>

      {/* Hero Section */}
      <Container maxWidth="lg" sx={{ mt: 8, mb: 4, flexGrow: 1 }}>
        <Grid container spacing={4} sx={{ alignItems: 'center' }}>
          <Grid xs={12} md={6}>
            <Box sx={{ pr: { md: 4 } }}>
              <Typography variant="h2" component="h1" gutterBottom sx={{ fontWeight: '800', lineHeight: 1.2 }}>
                Your Second Brain, <br />
                <Typography variant="h2" component="span" color="primary" sx={{ fontWeight: '800' }}>
                  Simplified.
                </Typography>
              </Typography>
              <Typography variant="h6" color="text.secondary" sx={{ mb: 4, fontWeight: '400' }}>
                Store, manage, and retrieve your notes and documents. Built with a fast FastAPI backend, a responsive React interface, and direct-to-S3 secure storage using Backblaze B2.
              </Typography>
              <Button
                variant="contained"
                size="large"
                color="primary"
                onClick={() => {
                  document.getElementById('upload-section').scrollIntoView({ behavior: 'smooth' })
                }}
                sx={{ py: 1.5, px: 4, borderRadius: 2, fontWeight: 'bold' }}
              >
                Get Started
              </Button>
            </Box>
          </Grid>

          {/* Interactive Upload Section */}
          <Grid xs={12} md={6} id="upload-section">
            <Card elevation={4} sx={{ borderRadius: 3, p: 2, backgroundColor: 'background.paper' }}>
              <CardContent>
                <Typography variant="h5" component="h2" gutterBottom sx={{ fontWeight: 'bold', mb: 2 }}>
                  Secure File Upload
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Directly upload your notes and documents to our Backblaze B2 S3 storage using temporary presigned URLs.
                </Typography>

                <Paper
                  variant="outlined"
                  sx={{
                    p: 4,
                    textAlign: 'center',
                    borderStyle: 'dashed',
                    borderColor: file ? 'primary.main' : 'text.disabled',
                    backgroundColor: 'action.hover',
                    cursor: 'pointer',
                    borderRadius: 2,
                    mb: 3,
                    transition: 'border-color 0.2s',
                    '&:hover': {
                      borderColor: 'primary.main',
                    },
                  }}
                  component="label"
                >
                  <input
                    type="file"
                    hidden
                    onChange={handleFileChange}
                    accept=".txt,.md,.pdf,.docx"
                    disabled={uploading}
                  />
                  <Typography variant="h6" gutterBottom color={file ? 'primary' : 'text.primary'}>
                    {file ? file.name : 'Select Note / Document'}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {file ? `${(file.size / 1024).toFixed(2)} KB` : 'Click to browse files'}
                  </Typography>
                </Paper>

                {error && (
                  <Alert severity="error" sx={{ mb: 3 }}>
                    {error}
                  </Alert>
                )}

                {success && (
                  <Alert severity="success" sx={{ mb: 3 }}>
                    <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                      {success.message}
                    </Typography>
                    <Typography variant="caption" display="block" sx={{ mt: 1, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                      Key: {success.key}
                    </Typography>
                  </Alert>
                )}

                {uploading && (
                  <Box sx={{ width: '100%', mb: 3 }}>
                    <LinearProgress variant="determinate" value={progress} />
                    <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block', textAlign: 'right' }}>
                      Uploading: {progress}%
                    </Typography>
                  </Box>
                )}

                <Button
                  variant="contained"
                  fullWidth
                  color="primary"
                  size="large"
                  disabled={!file || uploading}
                  onClick={handleUpload}
                  sx={{ borderRadius: 2, py: 1.2, fontWeight: 'bold' }}
                >
                  {uploading ? 'Uploading...' : 'Upload directly to S3'}
                </Button>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        <Divider sx={{ my: 8 }} />

        {/* Features & Capabilities */}
        <Grid container spacing={4}>
          <Grid xs={12} sm={4}>
            <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 1 }}>
              S3 Direct Uploads
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Upload files directly from your browser to Backblaze B2 S3 storage, keeping the FastAPI backend fast and memory-efficient.
            </Typography>
          </Grid>
          <Grid xs={12} sm={4}>
            <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 1 }}>
              Supported formats
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Seamlessly supports plain text files (.txt), Markdown (.md), PDF documents (.pdf), and Microsoft Word files (.docx).
            </Typography>
          </Grid>
          <Grid xs={12} sm={4}>
            <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 1 }}>
              Secure & Temporary
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Presigned URLs expire automatically after 1 hour (3600 seconds), ensuring your data remains secure and unauthorized uploads are blocked.
            </Typography>
          </Grid>
        </Grid>
      </Container>

      {/* Footer */}
      <Box sx={{ py: 3, px: 2, mt: 'auto', backgroundColor: 'background.paper', textAlign: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          © {new Date().getFullYear()} Personal Knowledge Base. Built using React, Material UI, and FastAPI.
        </Typography>
      </Box>
    </Box>
  )
}

export default App
