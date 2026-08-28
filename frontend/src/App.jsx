import React, { useState, useEffect, useMemo } from 'react'
import {
  ThemeProvider,
  createTheme,
  CssBaseline,
  Container,
  Box,
  Alert,
  Typography,
  Snackbar,
  Button
} from '@mui/material'
import VisibilityIcon from '@mui/icons-material/Visibility'
import { pingSystem } from './apis/systemApi'
import {
  getUploadUrl,
  completeUpload,
  getViewUrl,
  fetchFiles,
  updateFileMetadata,
  deleteFile
} from './apis/documentApi'

import Header from './components/Header'
import SearchHeader from './components/SearchHeader'
import FileList from './components/FileList'
import EditMetadataDialog from './components/EditMetadataDialog'
import DeleteConfirmDialog from './components/DeleteConfirmDialog'
import AuthPage from './pages/AuthPage'

import {
  getToken,
  clearToken,
  decodeToken,
  saveToken,
  isAuthenticated
} from './services/authService'

// File validation mapping
const ALLOWED_EXTENSIONS = {
  'text/plain': '.txt',
  'text/markdown': '.md',
  'application/pdf': '.pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx'
}

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

  // Search filter state
  const [searchTerm, setSearchTerm] = useState('')

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

  // Check backend connectivity and load documents on mount (or token changes)
  useEffect(() => {
    const checkConnection = async () => {
      try {
        await pingSystem()
        setBackendStatus('online')
        if (isAuthenticated()) {
          loadDocuments()
        }
      } catch (err) {
        console.error('Backend connection check failed:', err)
        setBackendStatus('offline')
      }
    }
    checkConnection()
  }, [token])

  // Login handler
  const handleLoginSuccess = (accessToken, userEmail) => {
    saveToken(accessToken)
    localStorage.setItem('pkb_user_email', userEmail)
    const decoded = decodeToken(accessToken)
    setToken(accessToken)
    setCurrentUser({ id: decoded?.sub, email: userEmail })
  }

  // Logout handler
  const handleLogout = () => {
    clearToken()
    localStorage.removeItem('pkb_user_email')
    setToken(null)
    setCurrentUser(null)
    setDocuments([])
    setSuccess(null)
    setError(null)
  }

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
    const parsedTags = doc.tags ? doc.tags.split(',').map((t) => t.trim()).filter(Boolean) : []
    setEditTags(parsedTags)
    setTagInput('')
    setEditOpen(true)
  }

  // Add tag chip in form
  const handleAddTag = () => {
    const trimmed = tagInput.trim()
    if (!trimmed) return
    if (trimmed.length > 50) return

    const currentCombinedLength = editTags.join(',').length
    const projectedCombinedLength = editTags.length > 0 ? currentCombinedLength + 1 + trimmed.length : trimmed.length
    if (projectedCombinedLength > 100) return

    if (!editTags.includes(trimmed)) {
      setEditTags([...editTags, trimmed])
    }
    setTagInput('')
  }

  // Remove tag chip in form
  const handleRemoveTag = (tagToRemove) => {
    setEditTags(editTags.filter((t) => t !== tagToRemove))
  }

  // Submit metadata changes to database
  const handleSaveMetadata = async () => {
    if (!editingDoc) return
    
    const finalTitle = editTitle.trim().slice(0, 100)
    const finalDescription = editDescription.trim().slice(0, 255)
    const tagsString = editTags.join(',')

    if (tagsString.length > 100) {
      setError('Combined tags length cannot exceed 100 characters.')
      return
    }

    try {
      await updateFileMetadata(editingDoc.fileId, {
        title: finalTitle,
        description: finalDescription,
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
        key: null
      })
    } catch (err) {
      console.error('Failed to delete document:', err)
      setError(err.response?.data?.detail || err.message || 'Failed to delete file.')
    } finally {
      setDeleting(false)
    }
  }

  // Handle document upload directly to S3 storage via presigned URL
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
          key: key
        })
        setLastUploadedKey(key)
        setFile(null)
        loadDocuments()

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
        const isDocx = targetKey.toLowerCase().endsWith('.docx') || targetKey.toLowerCase().includes('.docx')
        const openUrl = isDocx
          ? `https://view.officeapps.live.com/op/view.aspx?src=${encodeURIComponent(viewUrl)}`
          : viewUrl
        window.open(openUrl, '_blank')
      }
    } catch (err) {
      console.error(err)
      setError(err.message || 'Failed to generate view URL.')
    } finally {
      setViewLoading(false)
    }
  }

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
            {/* Top Search & Upload Control */}
            <SearchHeader
              searchTerm={searchTerm}
              onSearchChange={setSearchTerm}
              file={file}
              onFileChange={handleFileChange}
              uploading={uploading}
              verifying={verifying}
              progress={progress}
              onUpload={handleUpload}
              onClearFile={() => setFile(null)}
            />

            {/* Alert Banners */}
            {error && (
              <Alert 
                severity="error" 
                onClose={() => setError(null)}
                sx={{ mb: 3, borderRadius: '8px', border: '1px solid #FECACA', backgroundColor: '#FEF2F2', color: '#991B1B' }}
              >
                {error}
              </Alert>
            )}

            {success && (
              <Alert 
                severity="success" 
                onClose={() => setSuccess(null)}
                action={
                  success.key && (
                    <Button
                      color="inherit"
                      size="small"
                      disabled={viewLoading}
                      startIcon={<VisibilityIcon fontSize="small" />}
                      onClick={() => handleViewFile(success.key)}
                      sx={{ textTransform: 'none', fontWeight: 700 }}
                    >
                      {viewLoading ? 'Opening...' : 'View File'}
                    </Button>
                  )
                }
                sx={{ mb: 3, borderRadius: '8px', border: '1px solid #BBF7D0', backgroundColor: '#F0FDF4', color: '#166534' }}
              >
                {success.message}
              </Alert>
            )}

            {/* Main Traditional File List / Table */}
            <FileList
              documents={documents}
              loadingDocs={loadingDocs}
              searchTerm={searchTerm}
              onOpen={handleViewFile}
              onEdit={handleStartEdit}
              onDelete={handlePromptDelete}
            />
          </Container>
        )}

        {/* Metadata Customization Modal */}
        <EditMetadataDialog
          open={editOpen}
          onClose={() => setEditOpen(false)}
          editingDoc={editingDoc}
          editTitle={editTitle}
          setEditTitle={setEditTitle}
          editDescription={editDescription}
          setEditDescription={setEditDescription}
          editTags={editTags}
          tagInput={tagInput}
          setTagInput={setTagInput}
          onAddTag={handleAddTag}
          onRemoveTag={handleRemoveTag}
          onSave={handleSaveMetadata}
        />

        {/* Delete Confirmation Modal */}
        <DeleteConfirmDialog
          open={deleteConfirmOpen}
          onClose={() => setDeleteConfirmOpen(false)}
          docToDelete={docToDelete}
          deleting={deleting}
          onConfirmDelete={handleConfirmDelete}
        />

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
