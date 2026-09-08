import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Alert,
  Button,
  Paper,
} from '@mui/material'
import VisibilityIcon from '@mui/icons-material/Visibility'
import ChecklistIcon from '@mui/icons-material/Checklist'
import {
  getUploadUrl,
  completeUpload,
  getViewUrl,
  fetchFiles,
  updateFileMetadata,
  deleteFile,
  searchDocuments,
  triggerRagIndexing,
} from '../apis/documentApi'
import { partitionForKnowledgeBase } from '../services/vaultSelectionService'
import { mergeSelection } from '../services/ragService'
import { useKnowledgeBaseFiles } from '../context/KnowledgeBaseFilesContext'

import SearchHeader from '../components/SearchHeader'
import FileList from '../components/FileList'
import SelectionToolbar from '../components/SelectionToolbar'
import EditMetadataDialog from '../components/EditMetadataDialog'
import DeleteConfirmDialog from '../components/DeleteConfirmDialog'

// File validation mapping
const ALLOWED_EXTENSIONS = {
  'text/plain': '.txt',
  'text/markdown': '.md',
  'application/pdf': '.pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx'
}

/**
 * frontend/src/pages/VaultPage.jsx
 *
 * Phase 8 §3 Step 6 — the existing document vault, extracted out of App.jsx.
 *
 * Owns every piece of vault state (upload, search, pagination, metadata edit,
 * delete) and renders the vault-only view. App.jsx now only composes pages via
 * MUI Tabs, so this page mounts/unmounts as the tab switches and reloads its
 * documents on entry.
 */

function VaultPage() {
  // System States
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [viewLoading, setViewLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [lastUploadedKey, setLastUploadedKey] = useState(null)

  // Document management & pagination states
  const [documents, setDocuments] = useState([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(50)
  const [totalDocsCount, setTotalDocsCount] = useState(0)

  // Search filter & AI state
  const [searchTerm, setSearchTerm] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [isFallbackSearch, setIsFallbackSearch] = useState(false)

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

  // Vault multi-select (selection mode entered via Select Files or long-press) + add-to-KB
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [selectionMode, setSelectionMode] = useState(false)
  const [addingToKb, setAddingToKb] = useState(false)
  const { selected: kbSelected, addDocs, previewAddDocs } = useKnowledgeBaseFiles()

  // Document loading & search AbortController references
  const loadDocsAbortRef = useRef(null)
  const abortControllerRef = useRef(null)
  const hasMountedRef = useRef(false)

  // Load verified files from database with pagination and AbortController cancellation
  const loadDocuments = useCallback(async (targetPage = page, targetLimit = rowsPerPage) => {
    if (loadDocsAbortRef.current) {
      loadDocsAbortRef.current.abort()
    }
    const controller = new AbortController()
    loadDocsAbortRef.current = controller

    setLoadingDocs(true)
    try {
      const res = await fetchFiles(targetLimit, targetPage * targetLimit, controller.signal)
      if (Array.isArray(res)) {
        setDocuments(res)
        setTotalDocsCount(res.length)
      } else if (res && Array.isArray(res.items)) {
        setDocuments(res.items)
        setTotalDocsCount(res.total ?? res.items.length)
      }
    } catch (err) {
      if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') {
        return
      }
      console.error('Failed to load documents:', err)
      setError('Failed to load documents page: ' + (err.message || 'Network error'))
    } finally {
      if (loadDocsAbortRef.current === controller) {
        setLoadingDocs(false)
      }
    }
  }, [page, rowsPerPage])

  // Load the vault on first mount; abort in-flight loads on unmount.
  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true
      loadDocuments()
    }
    return () => {
      if (loadDocsAbortRef.current) {
        loadDocsAbortRef.current.abort()
      }
    }
  }, [loadDocuments])

  // Refactored Search Execution Helper
  const executeSearch = useCallback(async (query, targetPage, targetRowsPerPage) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller

    setIsSearching(true)
    setLoadingDocs(true)
    try {
      const response = await searchDocuments(query, targetRowsPerPage, targetPage * targetRowsPerPage, controller.signal)
      const rawResults = response?.results || response || []
      const mappedDocs = rawResults.map((item) => {
        if (item && item.file) {
          const fileObj = { ...item.file }
          if (item.score !== undefined && item.score !== null) {
            fileObj.score = item.score
          }
          return fileObj
        }
        return item
      })
      const isFallback =
        response?.search_mode === 'fallback' ||
        response?.searchMode === 'fallback' ||
        Boolean(response?.isFallbackSearch)
      setIsFallbackSearch(isFallback)
      setDocuments(mappedDocs)
      setTotalDocsCount(response?.total ?? mappedDocs.length)
    } catch (err) {
      if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') {
        return // Quietly ignore aborted search request
      }
      console.error('Search request failed:', err)
      setError('Search operation failed: ' + (err.message || 'Network error'))
    } finally {
      if (abortControllerRef.current === controller) {
        setIsSearching(false)
        setLoadingDocs(false)
      }
    }
  }, [])

  // Handle search term input change
  const handleSearchChange = useCallback((val) => {
    setSearchTerm(val)
  }, [])

  // Effect 1 (Search Input Handler): Watch searchTerm with 350ms debounce
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!searchTerm.trim()) {
        setIsFallbackSearch(false)
        setIsSearching(false)
        loadDocuments(page, rowsPerPage)
        return
      }
      setPage(0)
      executeSearch(searchTerm, 0, rowsPerPage)
    }, 350)

    return () => clearTimeout(timer)
  }, [searchTerm, loadDocuments, executeSearch, page, rowsPerPage])

  // Handle selected file validation
  const handleFileChange = useCallback((e) => {
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
  }, [])

  // Handle starting metadata customization
  const handleStartEdit = useCallback((doc) => {
    setEditingDoc(doc)
    setEditTitle(doc.title || '')
    setEditDescription(doc.description || '')
    const parsedTags = doc.tags ? doc.tags.split(',').map((t) => t.trim()).filter(Boolean) : []
    setEditTags(parsedTags)
    setTagInput('')
    setEditOpen(true)
  }, [])

  // Add tag chip in form
  const handleAddTag = useCallback(() => {
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
  }, [tagInput, editTags])

  // Remove tag chip in form
  const handleRemoveTag = useCallback((tagToRemove) => {
    setEditTags((prevTags) => prevTags.filter((t) => t !== tagToRemove))
  }, [])

  // Submit metadata changes to database
  const handleSaveMetadata = useCallback(async () => {
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
  }, [editingDoc, editTitle, editDescription, editTags, loadDocuments])

  // Handle prompting deletion modal
  const handlePromptDelete = useCallback((doc) => {
    setDocToDelete(doc)
    setDeleteConfirmOpen(true)
  }, [])

  // Handle confirming file deletion
  const handleConfirmDelete = useCallback(async () => {
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
  }, [docToDelete, loadDocuments])

  // Handle document upload directly to S3 storage via presigned URL
  const handleUpload = useCallback(async () => {
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
  }, [file, loadDocuments, handleStartEdit])

  // Handle requesting presigned GET URL to view or read the file
  const handleViewFile = useCallback(async (keyToView) => {
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
  }, [lastUploadedKey])

  // ── Vault selection (selection mode via Select Files / long-press) ──────
  const handleToggleSelect = useCallback((fileId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(fileId)) next.delete(fileId)
      else next.add(fileId)
      return next
    })
  }, [])

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set())
    setSelectionMode(false)
  }, [])

  const handleEnterSelectionMode = useCallback(() => {
    setSelectionMode(true)
  }, [])

  const handleLongPress = useCallback((fileId) => {
    setSelectionMode(true)
    setSelectedIds((prev) => {
      if (prev.has(fileId)) return prev
      const next = new Set(prev)
      next.add(fileId)
      return next
    })
  }, [])

  const handleBulkAddToKnowledgeBase = useCallback(async () => {
    const selectedDocs = documents.filter((d) => selectedIds.has(d.fileId))
    if (selectedDocs.length === 0) return
    const { toIndex, alreadyIndexed } = partitionForKnowledgeBase(selectedDocs)
    const preview = previewAddDocs(selectedDocs)
    setAddingToKb(true)
    setError(null)
    setSuccess(null)
    try {
      if (toIndex.length > 0) {
        const results = await Promise.allSettled(toIndex.map((d) => triggerRagIndexing(d.fileId)))
        const failed = results.filter((r) => r.status === 'rejected')
        if (failed.length > 0) {
          setError(
            `Failed to add ${failed.length} of ${toIndex.length} document(s) to the Knowledge Base.`,
          )
        }
      }
      // Merge only already-indexed docs into the shared KB selection (cap 5).
      if (preview.added > 0) addDocs(selectedDocs)
      if (toIndex.length > 0 && alreadyIndexed.length === 0) {
        let msg =
          toIndex.length === 1
            ? `1 document added to the Knowledge Base. Indexing started.`
            : `${toIndex.length} documents added to the Knowledge Base. Indexing started.`
        if (preview.skippedNotIndexed > 0) msg += ` ${preview.skippedNotIndexed} not yet indexed — will be selectable once indexing finishes.`
        if (preview.skippedCap > 0) msg += ` ${preview.skippedCap} skipped: at most 5 documents can be selected for the Knowledge Base.`
        setSuccess({ message: msg, key: null })
      } else if (toIndex.length > 0 && alreadyIndexed.length > 0) {
        let msg = `${toIndex.length} document(s) added to the Knowledge Base. ${alreadyIndexed.length} already indexed.`
        if (preview.added > 0) msg += ` ${preview.added} added to your Knowledge Base selection.`
        if (preview.skippedCap > 0) msg += ` ${preview.skippedCap} skipped: selection is capped at 5.`
        if (preview.skippedNotIndexed > 0) msg += ` ${preview.skippedNotIndexed} still indexing.`
        setSuccess({ message: msg, key: null })
      } else {
        let msg = 'Selected documents are already in the Knowledge Base.'
        if (preview.added > 0) msg += ` ${preview.added} added to your Knowledge Base selection.`
        else if (preview.skippedCap > 0) msg = 'Knowledge Base selection is full (at most 5 documents). Remove one to add more.'
        else if (preview.skippedAlreadyPresent > 0) msg += ' Already in your selection.'
        setSuccess({ message: msg, key: null })
      }
      setSelectedIds(new Set())
      setSelectionMode(false)
      loadDocuments()
    } catch (err) {
      setError(err.message || 'Failed to add documents to the Knowledge Base.')
    } finally {
      setAddingToKb(false)
    }
  }, [documents, selectedIds, loadDocuments, addDocs, previewAddDocs])

  const handleSingleAddToKnowledgeBase = useCallback(
    async (doc) => {
      const { toIndex } = partitionForKnowledgeBase([doc])
      setAddingToKb(true)
      setError(null)
      setSuccess(null)
      try {
        if (toIndex.length === 0) {
          const preview = mergeSelection(kbSelected, [doc])
          if (preview.added > 0) addDocs([doc])
          if (preview.skippedCap > 0) {
            setError('Knowledge Base selection is full (at most 5 documents). Remove one to add more.')
          } else if (preview.skippedAlreadyPresent > 0) {
            setSuccess({ message: `"${doc.title || doc.filename}" is already selected in the Knowledge Base.`, key: null })
          } else {
            setSuccess({ message: `"${doc.title || doc.filename}" added to your Knowledge Base selection.`, key: null })
          }
          return
        }
        await triggerRagIndexing(doc.fileId)
        setSuccess({ message: `"${doc.title || doc.filename}" added to the Knowledge Base. Indexing started. It will be selectable once indexing finishes.`, key: null })
        loadDocuments()
      } catch (err) {
        setError(err.message || 'Failed to add document to the Knowledge Base.')
      } finally {
        setAddingToKb(false)
      }
    },
    [loadDocuments, addDocs, kbSelected],
  )

  // Pagination Change Handlers (re-run the active search, else reload the list)
  const handlePageChange = useCallback((event, newPage) => {
    setPage(newPage)
    if (searchTerm.trim()) {
      executeSearch(searchTerm, newPage, rowsPerPage)
    } else {
      loadDocuments(newPage, rowsPerPage)
    }
  }, [loadDocuments, rowsPerPage, searchTerm, executeSearch])

  const handleRowsPerPageChange = useCallback((event) => {
    const newLimit = parseInt(event.target.value, 10)
    setRowsPerPage(newLimit)
    setPage(0)
    if (searchTerm.trim()) {
      executeSearch(searchTerm, 0, newLimit)
    } else {
      loadDocuments(0, newLimit)
    }
  }, [loadDocuments, searchTerm, executeSearch])

  return (
    <>
      <SearchHeader
        searchTerm={searchTerm}
        onSearchChange={handleSearchChange}
        isSearching={isSearching}
        file={file}
        onFileChange={handleFileChange}
        uploading={uploading}
        verifying={verifying}
        progress={progress}
        onUpload={handleUpload}
        onClearFile={() => setFile(null)}
      />

      {/* Selection strip below the search bar: Select Files button or the dark selection toolbar */}
      {selectionMode ? (
        <SelectionToolbar
          selectedCount={selectedIds.size}
          onClear={handleClearSelection}
          onAddToKnowledgeBase={handleBulkAddToKnowledgeBase}
          disabled={addingToKb || selectedIds.size === 0}
        />
      ) : (
        <Paper
          elevation={0}
          sx={{
            p: 1.5,
            mb: 4,
            borderRadius: '12px',
            backgroundColor: '#FFFFFF',
            border: '1px solid #E2E8F0',
            display: 'flex',
            justifyContent: 'flex-start',
          }}
        >
          <Button
            variant="outlined"
            startIcon={<ChecklistIcon />}
            onClick={handleEnterSelectionMode}
            sx={{
              color: '#0A192F',
              borderColor: '#E2E8F0',
              textTransform: 'none',
              fontWeight: 700,
              fontSize: '0.85rem',
              borderRadius: '8px',
              px: 2,
              '&:hover': { borderColor: '#0A192F', backgroundColor: '#F8FAFC' },
            }}
          >
            Select Files
          </Button>
        </Paper>
      )}

      {/* Fallback Alert Banner */}
      {isFallbackSearch && searchTerm.trim() && (
        <Alert
          severity="info"
          onClose={() => setIsFallbackSearch(false)}
          sx={{ mb: 3, borderRadius: '8px', border: '1px solid #BAE6FD', backgroundColor: '#F0F9FF', color: '#0369A1' }}
        >
          Semantic AI search returned no vector matches or is offline. Displaying keyword search results instead.
        </Alert>
      )}

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
        onAddToKnowledgeBase={handleSingleAddToKnowledgeBase}
        selectedIds={selectedIds}
        onToggleSelect={handleToggleSelect}
        selectionMode={selectionMode}
        onLongPress={handleLongPress}
        page={page}
        rowsPerPage={rowsPerPage}
        totalCount={totalDocsCount}
        onPageChange={handlePageChange}
        onRowsPerPageChange={handleRowsPerPageChange}
      />

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
    </>
  )
}

export default VaultPage