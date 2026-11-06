import React, { useState, useEffect, useRef, useCallback } from 'react'
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
  Tooltip
} from '@mui/material'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import DeleteSweepOutlinedIcon from '@mui/icons-material/DeleteSweepOutlined'
import CloseIcon from '@mui/icons-material/Close'
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf'
import DescriptionIcon from '@mui/icons-material/Description'
import TextSnippetIcon from '@mui/icons-material/TextSnippet'
import CodeIcon from '@mui/icons-material/Code'
import InsertDriveFileIcon from '@mui/icons-material/InsertDriveFile'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import ChatBubbleOutlinedIcon from '@mui/icons-material/ChatBubbleOutlined'

import { streamRagQuery } from '../apis/ragApi'
import { toFileIds, MAX_SELECTED_FILES, formatSelectionLabel } from '../services/ragService'
import { loadSession, saveSession, clearSession } from '../services/ragHistoryService'
import { useKnowledgeBaseFiles } from '../context/KnowledgeBaseFilesContext'

import RagMessageBubble from '../components/RagMessageBubble'

function getFileIcon(contentType, filename) {
  const name = (filename || '').toLowerCase()
  if (contentType === 'application/pdf' || name.endsWith('.pdf')) {
    return <PictureAsPdfIcon sx={{ color: '#DC2626', fontSize: 16 }} />
  }
  if (name.endsWith('.docx') || contentType?.includes('wordprocessingml')) {
    return <DescriptionIcon sx={{ color: '#2563EB', fontSize: 16 }} />
  }
  if (contentType === 'text/markdown' || name.endsWith('.md')) {
    return <CodeIcon sx={{ color: '#0284C7', fontSize: 16 }} />
  }
  if (contentType === 'text/plain' || name.endsWith('.txt')) {
    return <TextSnippetIcon sx={{ color: '#16A34A', fontSize: 16 }} />
  }
  return <InsertDriveFileIcon sx={{ color: '#64748B', fontSize: 16 }} />
}

/**
 * frontend/src/pages/KnowledgeBase.jsx
 *
 * ChatGPT-inspired conversational interface for the Knowledge Base.
 * - Conversation stream occupies the main vertical area.
 * - Input bar is docked at the bottom of the page.
 * - Selected documents appear as contextual attachment pills above the input bar.
 * - Clean, minimal chat layout with readable typography and proper message alignment.
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
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: 'calc(100vh - 64px)',
        backgroundColor: '#F8FAFC',
        position: 'relative'
      }}
    >
      {/* Top Knowledge Base Bar */}
      <Box
        sx={{
          px: { xs: 2, sm: 3 },
          py: 1.5,
          borderBottom: '1px solid #E2E8F0',
          backgroundColor: '#FFFFFF',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 32,
              height: 32,
              borderRadius: '8px',
              backgroundColor: '#0A192F',
              color: '#FFFFFF'
            }}
          >
            <AutoAwesomeIcon sx={{ fontSize: 18 }} />
          </Box>
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#0F172A', lineHeight: 1.2 }}>
              Knowledge Base
            </Typography>
            <Typography variant="caption" sx={{ color: '#64748B' }}>
              ChatGPT-style AI queries grounded in verified documents
            </Typography>
          </Box>
        </Box>

        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
          <Chip
            icon={<InfoOutlinedIcon sx={{ fontSize: '14px !important' }} />}
            label={`${selected.length} / ${MAX_SELECTED_FILES} documents`}
            size="small"
            sx={{
              height: 26,
              fontSize: '0.75rem',
              fontWeight: 700,
              backgroundColor: selected.length ? '#EFF6FF' : '#F1F5F9',
              color: selected.length ? '#1D4ED8' : '#64748B',
              border: '1px solid',
              borderColor: selected.length ? '#BFDBFE' : '#E2E8F0'
            }}
          />

          {(messages.length > 0 || selected.length > 0) && (
            <Button
              size="small"
              variant="outlined"
              startIcon={<DeleteSweepOutlinedIcon fontSize="small" />}
              onClick={handleNewConversation}
              disabled={sending}
              sx={{
                color: '#64748B',
                borderColor: '#E2E8F0',
                textTransform: 'none',
                fontWeight: 600,
                fontSize: '0.8rem',
                borderRadius: '8px',
                '&:hover': { borderColor: '#0A192F', color: '#0A192F', backgroundColor: '#F8FAFC' }
              }}
            >
              New Chat
            </Button>
          )}
        </Stack>
      </Box>

      {/* Main Conversation Stream */}
      <Box
        sx={{
          flexGrow: 1,
          overflowY: 'auto',
          px: { xs: 2, sm: 3 },
          py: 3,
          display: 'flex',
          flexDirection: 'column'
        }}
      >
        <Box sx={{ maxWidth: '820px', width: '100%', mx: 'auto', flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          {messages.length === 0 ? (
            <Box
              sx={{
                flexGrow: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                textAlign: 'center',
                py: 6,
                px: 2
              }}
            >
              <Box
                sx={{
                  width: 56,
                  height: 56,
                  borderRadius: '16px',
                  backgroundColor: '#0A192F',
                  color: '#FFFFFF',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  mb: 2.5,
                  boxShadow: '0 4px 12px rgba(10, 25, 47, 0.15)'
                }}
              >
                <AutoAwesomeIcon sx={{ fontSize: 30 }} />
              </Box>

              <Typography variant="h5" sx={{ fontWeight: 800, color: '#0F172A', mb: 1 }}>
                How can I help with your documents?
              </Typography>
              <Typography variant="body2" sx={{ color: '#64748B', maxWidth: 480, mb: 3, lineHeight: 1.6 }}>
                Ask questions about your selected documents. Answers are synthesized, cited, and strictly grounded in the document text.
              </Typography>

              {selected.length === 0 ? (
                <Paper
                  elevation={0}
                  sx={{
                    p: 2.5,
                    borderRadius: '12px',
                    border: '1px dashed #CBD5E1',
                    backgroundColor: '#FFFFFF',
                    maxWidth: 500,
                    width: '100%'
                  }}
                >
                  <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', justifyContent: 'center' }}>
                    <ChatBubbleOutlinedIcon sx={{ color: '#94A3B8' }} />
                    <Typography variant="body2" sx={{ color: '#475569', fontWeight: 500 }}>
                      No documents selected. Open the <strong>Vault</strong>, choose up to 5 documents, and click <strong>Add to Knowledge Base</strong>.
                    </Typography>
                  </Stack>
                </Paper>
              ) : (
                <Paper
                  elevation={0}
                  sx={{
                    p: 2,
                    borderRadius: '12px',
                    border: '1px solid #E2E8F0',
                    backgroundColor: '#FFFFFF',
                    maxWidth: 560,
                    width: '100%',
                    textAlign: 'left'
                  }}
                >
                  <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', mb: 1 }}>
                    Ready to query ({selected.length} active documents):
                  </Typography>
                  <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
                    {selected.map((doc) => (
                      <Chip
                        key={doc.fileId}
                        icon={getFileIcon(doc.contentType, doc.filename)}
                        label={formatSelectionLabel(doc)}
                        size="small"
                        onDelete={() => removeDoc(doc.fileId)}
                        sx={{
                          backgroundColor: '#F8FAFC',
                          border: '1px solid #E2E8F0',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          color: '#1E293B'
                        }}
                      />
                    ))}
                  </Stack>
                </Paper>
              )}
            </Box>
          ) : (
            <Stack spacing={2.5} sx={{ pb: 2 }}>
              {messages.map((msg, idx) => (
                <RagMessageBubble key={idx} message={msg} />
              ))}
              <div ref={chatEndRef} />
            </Stack>
          )}
        </Box>
      </Box>

      {/* Docked Bottom Chat Input Bar */}
      <Box
        sx={{
          flexShrink: 0,
          borderTop: '1px solid #E2E8F0',
          backgroundColor: '#FFFFFF',
          px: { xs: 2, sm: 3 },
          py: 2
        }}
      >
        <Box sx={{ maxWidth: '820px', width: '100%', mx: 'auto' }}>
          {/* Selected documents context pills right above input */}
          {selected.length > 0 && (
            <Box sx={{ mb: 1.5, display: 'flex', alignItems: 'center', gap: 1, overflowX: 'auto', pb: 0.5 }}>
              <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', whiteSpace: 'nowrap' }}>
                Context:
              </Typography>
              <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'nowrap' }}>
                {selected.map((doc) => (
                  <Chip
                    key={doc.fileId}
                    icon={getFileIcon(doc.contentType, doc.filename)}
                    label={formatSelectionLabel(doc)}
                    size="small"
                    onDelete={() => removeDoc(doc.fileId)}
                    sx={{
                      backgroundColor: '#F1F5F9',
                      border: '1px solid #E2E8F0',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      color: '#0F172A',
                      maxWidth: 220,
                      '& .MuiChip-label': {
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                      }
                    }}
                  />
                ))}
              </Stack>
            </Box>
          )}

          {/* ChatGPT-style Input Capsule */}
          <Paper
            elevation={0}
            sx={{
              display: 'flex',
              alignItems: 'flex-end',
              p: '6px 10px',
              borderRadius: '16px',
              backgroundColor: '#F8FAFC',
              border: '1px solid #CBD5E1',
              transition: 'border-color 0.2s, box-shadow 0.2s',
              '&:focus-within': {
                borderColor: '#0A192F',
                backgroundColor: '#FFFFFF',
                boxShadow: '0 0 0 3px rgba(10, 25, 47, 0.08)'
              }
            }}
          >
            <TextField
              fullWidth
              multiline
              maxRows={5}
              placeholder={
                selected.length < 1
                  ? 'Select documents in the Vault to ask questions…'
                  : 'Ask anything about your selected documents…'
              }
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={sending}
              variant="standard"
              slotProps={{
                input: {
                  disableUnderline: true,
                  sx: {
                    px: 1,
                    py: 0.75,
                    fontSize: '0.925rem',
                    color: '#0F172A',
                    lineHeight: 1.5
                  }
                }
              }}
            />

            <Tooltip title={!canSend ? (selected.length < 1 ? 'Select documents in Vault' : 'Enter a prompt') : 'Send (Enter)'}>
              <span>
                <IconButton
                  color="primary"
                  disabled={!canSend}
                  onClick={handleSend}
                  aria-label="Send question"
                  sx={{
                    width: 36,
                    height: 36,
                    backgroundColor: canSend ? '#0A192F' : '#E2E8F0',
                    color: canSend ? '#FFFFFF' : '#94A3B8',
                    borderRadius: '10px',
                    mb: 0.25,
                    ml: 0.5,
                    transition: 'all 0.15s',
                    '&:hover': {
                      backgroundColor: canSend ? '#0F172A' : '#E2E8F0'
                    },
                    '&.Mui-disabled': {
                      backgroundColor: '#E2E8F0',
                      color: '#94A3B8'
                    }
                  }}
                >
                  <ArrowUpwardIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Paper>

          {/* Accessibility & Input Instructions */}
          <Typography
            variant="caption"
            sx={{
              display: 'block',
              textAlign: 'center',
              color: '#94A3B8',
              mt: 1,
              fontSize: '0.72rem'
            }}
          >
            {selected.length < 1
              ? 'Select documents in the Vault to enable querying.'
              : 'Answers are strictly grounded in selected documents. Press Enter to send, Shift + Enter for new line.'}
          </Typography>
        </Box>
      </Box>

      {/* Snackbar alerts */}
      <Snackbar
        open={Boolean(snackbar)}
        autoHideDuration={6000}
        onClose={() => setSnackbar(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snackbar?.severity || 'info'} variant="filled" onClose={() => setSnackbar(null)} sx={{ width: '100%', borderRadius: '8px' }}>
          {snackbar?.message}
        </Alert>
      </Snackbar>
    </Box>
  )
}

export default React.memo(KnowledgeBase)
