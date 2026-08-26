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
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Chip
} from '@mui/material'
import { pingSystem } from './apis/systemApi'
import { getUploadUrl, completeUpload, getViewUrl, fetchFiles, updateFileMetadata, deleteFile } from './apis/documentApi'


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

const TrashIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 6h18" />
    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
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

  // Document management states
  const [documents, setDocuments] = useState([])
  const [loadingDocs, setLoadingDocs] = useState(false)

  // Edit metadata modal states
  const [editOpen, setEditOpen] = useState(false)
  const [editingDoc, setEditingDoc] = useState(null)
  const [editTitle, setEditTitle] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editTags, setEditTags] = useState([])
  const [tagInput, setTagInput] = useState('')

  // Delete modal states
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [docToDelete, setDocToDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)


  // Load verified files from database
  const loadDocuments = async () => {
    setLoadingDocs(true)
    try {
      const docs = await fetchFiles()
      setDocuments(docs)
    } catch (err) {
      console.error('Failed to load documents:', err)
    } finally {
      setLoadingDocs(false)
    }
  }

  // Check backend connectivity and load documents on mount
  useEffect(() => {
    const checkConnection = async () => {
      try {
        await pingSystem()
        setBackendStatus('online')
        loadDocuments()
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

  // Handle starting metadata customization
  const handleStartEdit = (doc) => {
    setEditingDoc(doc)
    setEditTitle(doc.title || '')
    setEditDescription(doc.description || '')
    const parsedTags = doc.tags ? doc.tags.split(',').map(t => t.trim()).filter(Boolean) : []
    setEditTags(parsedTags)
    setTagInput('')
    setEditOpen(true)
  }

  // Add tag chip in form
  const handleAddTag = () => {
    const trimmed = tagInput.trim()
    if (trimmed && !editTags.includes(trimmed)) {
      setEditTags([...editTags, trimmed])
    }
    setTagInput('')
  }

  // Remove tag chip in form
  const handleRemoveTag = (tagToRemove) => {
    setEditTags(editTags.filter(t => t !== tagToRemove))
  }

  // Submit metadata changes to database
  const handleSaveMetadata = async () => {
    if (!editingDoc) return
    try {
      const tagsString = editTags.join(',')
      await updateFileMetadata(editingDoc.fileId, {
        title: editTitle,
        description: editDescription,
        tags: tagsString
      })
      setEditOpen(false)
      loadDocuments()
      setSuccess({
        message: 'Document metadata updated successfully.',
        key: editingDoc.s3Key
      })
    } catch (err) {
      console.error('Failed to save metadata:', err)
      setError(err.message || 'Failed to update metadata.')
    }
  }

  // Handle prompting deletion modal
  const handlePromptDelete = (doc) => {
    setDocToDelete(doc)
    setDeleteConfirmOpen(true)
  }

  // Handle confirming file deletion
  const handleConfirmDelete = async () => {
    if (!docToDelete) return

    setDeleting(true)
    setError(null)
    setSuccess(null)
    try {
      await deleteFile(docToDelete.fileId)
      setDeleteConfirmOpen(false)
      const docName = docToDelete.title || docToDelete.filename
      setDocToDelete(null)
      loadDocuments()
      setSuccess({
        message: `Document "${docName}" permanently deleted.`,
        key: null,
      })
    } catch (err) {
      console.error('Failed to delete document:', err)
      setError(err.response?.data?.detail || err.message || 'Failed to delete file.')
    } finally {
      setDeleting(false)
    }
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
        loadDocuments() // Refresh list

        // Prompt metadata customization immediately after file upload
        if (verifyRes.metadata) {
          handleStartEdit(verifyRes.metadata)
        }
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

  // Helper functions for metadata presentation
  const getFileTypeIcon = (contentType, filename) => {
    const name = (filename || '').toLowerCase()
    if (contentType === 'application/pdf' || name.endsWith('.pdf')) {
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ff4d4f" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
          <path d="M14 2v4a2 2 0 0 0 2 2h4" />
          <path d="M9 15h6" />
          <path d="M9 11h6" />
        </svg>
      )
    }
    if (contentType === 'text/markdown' || name.endsWith('.md')) {
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1890ff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
          <path d="M14 2v4a2 2 0 0 0 2 2h4" />
          <path d="M9 13h6" />
          <path d="M9 17h6" />
        </svg>
      )
    }
    if (name.endsWith('.docx')) {
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#722ed1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
          <path d="M14 2v4a2 2 0 0 0 2 2h4" />
          <path d="M10 9H8" />
          <path d="M16 13H8" />
          <path d="M16 17H8" />
        </svg>
      )
    }
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#52c41a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
        <path d="M14 2v4a2 2 0 0 0 2 2h4" />
        <path d="M9 12h6" />
        <path d="M9 16h6" />
      </svg>
    )
  }

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
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

          {/* Document Library Section */}
          <Box sx={{ mt: 10, mb: 4 }}>
            <Typography variant="h5" sx={{ fontWeight: 800, mb: 1, letterSpacing: '-0.02em' }}>
              Document Vault
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>
              Your securely stored files and metadata. Click View to open or edit to modify details.
            </Typography>

            {loadingDocs ? (
              <Box sx={{ width: '100%', py: 4 }}>
                <LinearProgress sx={{ height: 2, borderRadius: 1 }} />
              </Box>
            ) : documents.length === 0 ? (
              <Paper 
                variant="outlined" 
                sx={{ 
                  py: 8, 
                  textAlign: 'center', 
                  borderColor: 'divider', 
                  backgroundColor: 'transparent',
                  borderStyle: 'dashed'
                }}
              >
                <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                  No verified documents found in vault. Select a file above and upload to begin.
                </Typography>
              </Paper>
            ) : (
              <Grid container spacing={3}>
                {documents.map((doc) => (
                  <Grid item xs={12} sm={6} md={4} key={doc.fileId}>
                    <Paper 
                      variant="outlined" 
                      sx={{ 
                        p: 3, 
                        height: '100%', 
                        display: 'flex', 
                        flexDirection: 'column', 
                        borderColor: 'divider',
                        borderRadius: '8px',
                        backgroundColor: 'background.paper',
                        transition: 'all 0.2s ease',
                        '&:hover': {
                          borderColor: 'text.primary',
                        }
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2, mb: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', mt: 0.5 }}>
                          {getFileTypeIcon(doc.contentType, doc.filename)}
                        </Box>
                        <Box sx={{ overflow: 'hidden', flexGrow: 1 }}>
                          <Typography 
                            variant="subtitle1" 
                            sx={{ 
                              fontWeight: 700, 
                              lineHeight: 1.3,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              mb: 0.5
                            }}
                          >
                            {doc.title || doc.filename}
                          </Typography>
                          <Typography 
                            variant="caption" 
                            color="text.secondary" 
                            sx={{ 
                              display: 'block',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap'
                            }}
                          >
                            {doc.filename}
                          </Typography>
                        </Box>
                      </Box>

                      <Typography 
                        variant="body2" 
                        color="text.secondary" 
                        sx={{ 
                          fontSize: '0.82rem',
                          lineHeight: 1.5,
                          mb: 3,
                          flexGrow: 1,
                          display: '-webkit-box',
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                          fontStyle: doc.description ? 'normal' : 'italic'
                        }}
                      >
                        {doc.description || 'No description provided.'}
                      </Typography>

                      {/* Display Tags */}
                      <Box sx={{ display: 'flex', gap: 0.8, flexWrap: 'wrap', mb: 3 }}>
                        {doc.tags ? (
                          doc.tags.split(',').map((tag) => (
                            <Chip 
                              key={tag.trim()} 
                              label={tag.trim()} 
                              variant="outlined"
                              size="small"
                              sx={{ 
                                borderRadius: '4px', 
                                fontSize: '0.72rem', 
                                fontWeight: 700,
                                height: 22,
                                borderColor: 'divider',
                                color: 'text.secondary'
                              }}
                            />
                          ))
                        ) : (
                          <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic', fontSize: '0.72rem' }}>
                            no tags
                          </Typography>
                        )}
                      </Box>

                      {/* Card Actions Footer */}
                      <Box 
                        sx={{ 
                          pt: 2, 
                          borderTop: '1px solid', 
                          borderColor: 'divider',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          gap: 1
                        }}
                      >
                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                          {formatFileSize(doc.sizeBytes)}
                        </Typography>
                        <Box sx={{ display: 'flex', gap: 1 }}>
                          <Button 
                            size="small" 
                            variant="outlined"
                            onClick={() => handleStartEdit(doc)}
                            sx={{ 
                              fontSize: '0.75rem',
                              py: 0.5,
                              px: 1.5,
                              borderColor: 'divider',
                              color: 'text.primary',
                              '&:hover': {
                                borderColor: 'text.primary',
                                backgroundColor: darkMode ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)'
                              }
                            }}
                          >
                            Edit
                          </Button>
                          <Button 
                            size="small" 
                            variant="contained"
                            onClick={() => handleViewFile(doc.s3Key)}
                            sx={{ 
                              fontSize: '0.75rem',
                              py: 0.5,
                              px: 1.5,
                              backgroundColor: 'text.primary',
                              color: 'background.default',
                              '&:hover': {
                                backgroundColor: 'background.default',
                                color: 'text.primary',
                                borderColor: 'text.primary',
                              }
                            }}
                          >
                            View
                          </Button>
                          <IconButton 
                            size="small"
                            onClick={() => handlePromptDelete(doc)}
                            title="Delete document"
                            sx={{ 
                              border: '1px solid', 
                              borderColor: 'divider', 
                              borderRadius: '6px',
                              color: '#ff4d4f',
                              p: '5px',
                              '&:hover': {
                                borderColor: '#ff4d4f',
                                backgroundColor: darkMode ? 'rgba(255, 77, 79, 0.12)' : 'rgba(255, 77, 79, 0.06)'
                              }
                            }}
                          >
                            <TrashIcon />
                          </IconButton>
                        </Box>

                      </Box>
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            )}
          </Box>
        </Container>

        {/* Metadata Customization Dialog */}
        <Dialog 
          open={editOpen} 
          onClose={() => setEditOpen(false)}
          fullWidth
          maxWidth="sm"
          PaperProps={{
            sx: {
              backgroundColor: 'background.paper',
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: '8px',
              backgroundImage: 'none',
              boxShadow: 'none',
              p: 2
            }
          }}
        >
          <DialogTitle sx={{ fontWeight: 700, fontSize: '1.25rem', letterSpacing: '-0.02em', px: 3, pt: 2, pb: 1 }}>
            Customize File Details
          </DialogTitle>
          <DialogContent sx={{ px: 3, py: 2, display: 'flex', flexDirection: 'column', gap: 3 }}>
            <div>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, textTransform: 'uppercase', display: 'block', mb: 1 }}>
                Original File
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 2, border: '1px solid', borderColor: 'divider', borderRadius: '6px', backgroundColor: darkMode ? 'rgba(255, 255, 255, 0.01)' : 'rgba(0, 0, 0, 0.005)' }}>
                {editingDoc && getFileTypeIcon(editingDoc.contentType, editingDoc.filename)}
                <Typography sx={{ fontSize: '0.85rem', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {editingDoc?.filename}
                </Typography>
              </Box>
            </div>

            <TextField
              label="Document Title"
              fullWidth
              variant="outlined"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              placeholder="e.g. Q3 Financial Statement"
              InputLabelProps={{ shrink: true }}
              sx={{
                '& .MuiOutlinedInput-root': {
                  borderRadius: '6px',
                  '& fieldset': { borderColor: 'divider' },
                  '&:hover fieldset': { borderColor: 'text.primary' },
                }
              }}
            />

            <TextField
              label="Description"
              fullWidth
              multiline
              rows={3}
              variant="outlined"
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              placeholder="Brief summary of the document contents..."
              InputLabelProps={{ shrink: true }}
              sx={{
                '& .MuiOutlinedInput-root': {
                  borderRadius: '6px',
                  '& fieldset': { borderColor: 'divider' },
                  '&:hover fieldset': { borderColor: 'text.primary' },
                }
              }}
            />

            {/* Chip Tag Input Component */}
            <div>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, textTransform: 'uppercase', display: 'block', mb: 1.5 }}>
                Tags
              </Typography>
              
              <Box sx={{ display: 'flex', gap: 1.5, mb: 2 }}>
                <TextField
                  placeholder="Add a tag and press Enter"
                  size="small"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddTag();
                    }
                  }}
                  sx={{
                    flexGrow: 1,
                    '& .MuiOutlinedInput-root': {
                      borderRadius: '6px',
                      '& fieldset': { borderColor: 'divider' },
                      '&:hover fieldset': { borderColor: 'text.primary' },
                    }
                  }}
                />
                <Button 
                  variant="outlined" 
                  onClick={handleAddTag}
                  sx={{
                    borderColor: 'divider',
                    color: 'text.primary',
                    '&:hover': {
                      borderColor: 'text.primary',
                      backgroundColor: darkMode ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)'
                    }
                  }}
                >
                  Add
                </Button>
              </Box>

              {/* Tag Chips List */}
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', minHeight: 32 }}>
                {editTags.length === 0 ? (
                  <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic', alignSelf: 'center' }}>
                    No tags added yet.
                  </Typography>
                ) : (
                  editTags.map((tag) => (
                    <Chip
                      key={tag}
                      label={tag}
                      onDelete={() => handleRemoveTag(tag)}
                      variant="outlined"
                      sx={{
                        borderRadius: '4px',
                        borderColor: 'divider',
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        backgroundColor: darkMode ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.01)',
                        '& .MuiChip-deleteIcon': {
                          color: 'text.secondary',
                          '&:hover': { color: '#ff4d4f' }
                        }
                      }}
                    />
                  ))
                )}
              </Box>
            </div>
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2, gap: 1.5 }}>
            <Button 
              onClick={() => setEditOpen(false)}
              sx={{
                color: 'text.secondary',
                '&:hover': { color: 'text.primary' }
              }}
            >
              Cancel
            </Button>
            <Button 
              variant="contained" 
              onClick={handleSaveMetadata}
              sx={{
                backgroundColor: 'text.primary',
                color: 'background.default',
                '&:hover': {
                  backgroundColor: 'background.default',
                  color: 'text.primary',
                  borderColor: 'text.primary',
                }
              }}
            >
              Save Changes
            </Button>
          </DialogActions>
        </Dialog>

        {/* Delete Confirmation Modal */}
        <Dialog 
          open={deleteConfirmOpen} 
          onClose={() => !deleting && setDeleteConfirmOpen(false)}
          fullWidth
          maxWidth="xs"
          PaperProps={{
            sx: {
              backgroundColor: 'background.paper',
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: '8px',
              backgroundImage: 'none',
              boxShadow: 'none',
              p: 2
            }
          }}
        >
          <DialogTitle sx={{ fontWeight: 700, fontSize: '1.15rem', letterSpacing: '-0.02em', px: 2, pt: 1, pb: 1, color: '#ff4d4f', display: 'flex', alignItems: 'center', gap: 1 }}>
            <AlertIcon /> Confirm Permanent Deletion
          </DialogTitle>
          <DialogContent sx={{ px: 2, py: 1.5 }}>
            <Typography variant="body2" color="text.primary" sx={{ mb: 2, fontWeight: 500 }}>
              Are you sure you want to permanently delete <strong>{docToDelete?.title || docToDelete?.filename}</strong>?
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', p: 1.5, borderRadius: '6px', backgroundColor: darkMode ? 'rgba(255,77,79,0.08)' : 'rgba(255,77,79,0.04)', border: '1px solid rgba(255,77,79,0.2)' }}>
              This will permanently delete the file from Backblaze B2 cloud storage and MySQL database. This action cannot be undone.
            </Typography>
          </DialogContent>
          <DialogActions sx={{ px: 2, pb: 1, gap: 1 }}>
            <Button 
              disabled={deleting}
              onClick={() => setDeleteConfirmOpen(false)}
              sx={{
                color: 'text.secondary',
                '&:hover': { color: 'text.primary' }
              }}
            >
              Cancel
            </Button>
            <Button 
              variant="contained"
              disabled={deleting}
              onClick={handleConfirmDelete}
              sx={{
                backgroundColor: '#ff4d4f',
                color: '#ffffff',
                '&:hover': {
                  backgroundColor: '#d9363e',
                }
              }}
            >
              {deleting ? 'Deleting...' : 'Delete Document'}
            </Button>
          </DialogActions>
        </Dialog>


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
