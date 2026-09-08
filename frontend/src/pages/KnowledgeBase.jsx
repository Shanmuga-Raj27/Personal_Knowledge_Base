import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Box,
  Paper,
  Typography,
  Stack,
  TextField,
  IconButton,
  Snackbar,
  Alert,
  Button,
  Chip,
} from '@mui/material'
import SendIcon from '@mui/icons-material/Send'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import DeleteSweepOutlinedIcon from '@mui/icons-material/DeleteSweepOutlined'
import CloseIcon from '@mui/icons-material/Close'
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf'
import DescriptionIcon from '@mui/icons-material/Description'
import TextSnippetIcon from '@mui/icons-material/TextSnippet'
import CodeIcon from '@mui/icons-material/Code'
import InsertDriveFileIcon from '@mui/icons-material/InsertDriveFile'

import { streamRagQuery } from '../apis/ragApi'
import { toFileIds, MAX_SELECTED_FILES, formatSelectionLabel } from '../services/ragService'
import { loadSession, saveSession, clearSession } from '../services/ragHistoryService'
import { useKnowledgeBaseFiles } from '../context/KnowledgeBaseFilesContext'

import RagMessageBubble from '../components/RagMessageBubble'

function getFileIcon(contentType, filename) {
  const name = (filename || '').toLowerCase()
  if (contentType === 'application/pdf' || name.endsWith('.pdf')) {
    return <PictureAsPdfIcon sx={{ color: '#DC2626', fontSize: 18 }} />
  }
  if (name.endsWith('.docx') || contentType?.includes('wordprocessingml')) {
    return <DescriptionIcon sx={{ color: '#2563EB', fontSize: 18 }} />
  }
  if (contentType === 'text/markdown' || name.endsWith('.md')) {
    return <CodeIcon sx={{ color: '#0284C7', fontSize: 18 }} />
  }
  if (contentType === 'text/plain' || name.endsWith('.txt')) {
    return <TextSnippetIcon sx={{ color: '#16A34A', fontSize: 18 }} />
  }
  return <InsertDriveFileIcon sx={{ color: '#64748B', fontSize: 18 }} />
}

/**
 * frontend/src/pages/KnowledgeBase.jsx
 *
 * Knowledge Base composition root — now uses the shared selection context.
 * The document picker (DocumentMultiSelect) was removed; selection is made
 * in the Vault (Select Files / long-press -> Add to Knowledge Base) and
 * surfaces here as a compact list. Only this page + the shared context
 * know about the 5-doc cap.
 */
function KnowledgeBase({ userId }) {
  const { selected, removeDoc, clear } = useKnowledgeBaseFiles()

  const [sessionSeed] = useState(() => loadSession(userId))
  const [messages, setMessages] = useState(sessionSeed.messages)
  const [question, setQuestion] = useState('')
  const [sending, setSending] = useState(false)
  const [snackbar, setSnackbar] = useState(null)

  const messagesRef = useRef([])
  const chatEndRef = useRef(null)
  const queryAbortRef = useRef(null)

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  useEffect(() => {
    if (userId == null) return undefined
    const timer = setTimeout(() => {
      saveSession(userId, { messages, selected })
    }, 400)
    return () => clearTimeout(timer)
  }, [userId, messages, selected])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleNewConversation = useCallback(() => {
    if (sending) return
    clearSession(userId)
    clear()
    setMessages([])
    setQuestion('')
    setSnackbar({ severity: 'info', message: 'Started a new conversation.' })
  }, [userId, sending, clear])

  const handleSend = useCallback(async () => {
    const q = question.trim()
    if (!q || selected.length < 1 || sending) return

    const userMessage = { role: 'user', text: q }
    const placeholder = { role: 'assistant', text: '', streaming: true, sources: [], diagnostics: {} }
    const asstIndex = messagesRef.current.length + 1

    setMessages((prev) => [...prev, userMessage, placeholder])
    setQuestion('')
    setSending(true)
    setSnackbar(null)

    const controller = new AbortController()
    queryAbortRef.current = controller

    const onToken = (acc) => {
      setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, text: acc } : m)))
    }

    try {
      const result = await streamRagQuery(
        { question: q, file_ids: toFileIds(selected) },
        onToken,
        controller.signal,
      )

      setMessages((prev) =>
        prev.map((m, i) =>
          i === asstIndex
            ? {
                ...m,
                text: result.answer,
                sources: result.sources,
                diagnostics: result.diagnostics,
                streaming: false,
                ...(result.error ? { error: result.error } : {}),
              }
            : m,
        ),
      )
      if (result.error) {
        setSnackbar({ severity: 'error', message: result.error })
      }
    } catch (err) {
      const aborted = err.name === 'CanceledError' || err.code === 'ERR_CANCELED'
      if (aborted) return
      setMessages((prev) =>
        prev.map((m, i) =>
          i === asstIndex ? { ...m, streaming: false, error: err.message || 'Request failed.' } : m,
        ),
      )
      setSnackbar({ severity: 'error', message: err.message || 'Failed to get an answer.' })
    } finally {
      if (queryAbortRef.current === controller) queryAbortRef.current = null
      setSending(false)
    }
  }, [question, selected, sending])

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend],
  )

  const canSend = question.trim().length > 0 && selected.length >= 1 && !sending

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <AutoAwesomeIcon sx={{ color: '#0A192F' }} />
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 800, color: '#0F172A' }}>
            Knowledge Base
          </Typography>
          <Typography variant="caption" sx={{ color: '#64748B' }}>
            Ask a question about up to {MAX_SELECTED_FILES} of your indexed documents. Answers are grounded in their content.
          </Typography>
        </Box>
        <Box sx={{ flexGrow: 1 }} />
        {(messages.length > 0 || selected.length > 0) && (
          <Button
            size="small"
            variant="outlined"
            startIcon={<DeleteSweepOutlinedIcon />}
            onClick={handleNewConversation}
            disabled={sending}
            sx={{
              color: '#64748B',
              borderColor: '#E2E8F0',
              textTransform: 'none',
              fontWeight: 600,
              '&:hover': { borderColor: '#0A192F', color: '#0A192F' },
            }}
          >
            New conversation
          </Button>
        )}
      </Box>

      <Paper
        elevation={0}
        sx={{ p: 2, borderRadius: '12px', backgroundColor: '#FFFFFF', border: '1px solid #E2E8F0' }}
      >
        <Stack direction="row" spacing={1} alignItems="flex-end">
          <TextField
            fullWidth
            multiline
            maxRows={4}
            size="small"
            placeholder="Ask anything about the selected documents…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={sending}
            slotProps={{
              input: {
                sx: {
                  borderRadius: '8px',
                  backgroundColor: '#F8FAFC',
                  fontSize: '0.9rem',
                  '& fieldset': { borderColor: '#E2E8F0' },
                  '&:hover fieldset': { borderColor: '#0A192F' },
                  '&.Mui-focused fieldset': { borderColor: '#0A192F' },
                },
              },
            }}
          />
          <IconButton
            color="primary"
            disabled={!canSend}
            onClick={handleSend}
            aria-label="Send question"
            sx={{
              backgroundColor: canSend ? '#0A192F' : '#E2E8F0',
              color: canSend ? '#FFFFFF' : '#94A3B8',
              borderRadius: '8px',
              p: 1.25,
              '&:hover': {
                backgroundColor: canSend ? '#0F172A' : '#E2E8F0',
              },
            }}
          >
            <SendIcon fontSize="small" />
          </IconButton>
        </Stack>
        <Typography variant="caption" sx={{ color: '#94A3B8', display: 'block', mt: 0.75 }}>
          {selected.length < 1
            ? 'Select documents in the Vault to enable sending.'
            : !question.trim()
              ? 'Type a question to enable sending.'
              : 'Press Enter to send, Shift+Enter for a new line.'}
        </Typography>
      </Paper>

      <Paper
        elevation={0}
        sx={{ p: 2, borderRadius: '12px', backgroundColor: '#FFFFFF', border: '1px solid #E2E8F0' }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: selected.length ? 1.25 : 0 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#0F172A' }}>
            Selected documents
          </Typography>
          <Chip
            label={`${selected.length} / ${MAX_SELECTED_FILES}`}
            size="small"
            sx={{
              height: 22,
              fontSize: '0.75rem',
              fontWeight: 700,
              backgroundColor: selected.length ? '#EFF6FF' : '#F1F5F9',
              color: selected.length ? '#1E40AF' : '#64748B',
              border: '1px solid',
              borderColor: selected.length ? '#BFDBFE' : '#E2E8F0',
            }}
          />
        </Box>
        {selected.length === 0 ? (
          <Typography variant="body2" sx={{ color: '#94A3B8' }}>
            No documents selected. Go to the Vault, use <strong>Select Files</strong> or long-press a file, then Add to Knowledge Base.
          </Typography>
        ) : (
          <Stack spacing={1}>
            {selected.map((doc) => (
              <Box
                key={doc.fileId}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  p: 1,
                  borderRadius: '8px',
                  border: '1px solid #E2E8F0',
                  backgroundColor: '#F8FAFC',
                }}
              >
                {getFileIcon(doc.contentType, doc.filename)}
                <Typography
                  variant="body2"
                  sx={{ flexGrow: 1, fontWeight: 600, color: '#0F172A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {formatSelectionLabel(doc)}
                </Typography>
                <IconButton
                  size="small"
                  aria-label={`Remove ${formatSelectionLabel(doc)}`}
                  onClick={() => removeDoc(doc.fileId)}
                  sx={{ color: '#64748B', '&:hover': { backgroundColor: '#E2E8F0', color: '#0F172A' } }}
                >
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Box>
            ))}
          </Stack>
        )}
      </Paper>

      <Paper
        elevation={0}
        sx={{
          flexGrow: 1,
          minHeight: 340,
          maxHeight: '55vh',
          overflowY: 'auto',
          p: 2,
          borderRadius: '12px',
          backgroundColor: '#F8FAFC',
          border: '1px solid #E2E8F0',
          display: 'flex',
          flexDirection: 'column',
          gap: 1.5,
        }}
      >
        {messages.length === 0 ? (
          <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Typography variant="body2" sx={{ color: '#94A3B8', textAlign: 'center' }}>
              Select documents in the Vault and ask a question above.
              <br />
              Your grounded, cited answer will stream here.
            </Typography>
          </Box>
        ) : (
          messages.map((msg, idx) => <RagMessageBubble key={idx} message={msg} />)
        )}
        <div ref={chatEndRef} />
      </Paper>

      <Snackbar
        open={Boolean(snackbar)}
        autoHideDuration={6000}
        onClose={() => setSnackbar(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snackbar?.severity || 'info'} variant="filled" onClose={() => setSnackbar(null)} sx={{ width: '100%' }}>
          {snackbar?.message}
        </Alert>
      </Snackbar>
    </Box>
  )
}

export default KnowledgeBase
