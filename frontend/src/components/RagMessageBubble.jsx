import React, { useState } from 'react'
import {
  Box,
  Typography,
  Collapse,
  IconButton,
  Stack,
  Chip,
  Divider,
  Alert,
  Tooltip,
  Link,
  useTheme,
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ChatBubbleOutlineOutlinedIcon from '@mui/icons-material/ChatBubbleOutlineOutlined'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function formatPages(source) {
  if (source.page_start == null) return ''
  return source.page_start === source.page_end
    ? `Page ${source.page_start}`
    : `Pages ${source.page_start}–${source.page_end}`
}

const CITATION_BRACKET_RE =
  /\[(?:id|chunk_id)=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]/gi
const CITATION_BARE_RE =
  /(?:id|chunk_id)=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi

function sanitizeCitations(text, sources) {
  if (!text) return text
  const idToRef = new Map()
  ;(sources || []).forEach((s, idx) => {
    if (s?.chunk_id) idToRef.set(s.chunk_id.toLowerCase(), `[${idx + 1}]`)
  })
  let out = text.replace(CITATION_BRACKET_RE, (match, id) => idToRef.get(id.toLowerCase()) ?? '')
  out = out.replace(CITATION_BARE_RE, '')
  out = out.replace(/\[\s*\]/g, '').replace(/ {2,}/g, ' ')
  return out
}

function MarkdownContent({ children, isDark, textSecondary }) {
  const codeBlockSx = {
    mt: 1,
    mb: 1,
    p: 1.5,
    borderRadius: '8px',
    backgroundColor: isDark ? '#161922' : '#0F172A',
    color: '#E2E8F0',
    fontSize: '0.8125rem',
    fontFamily: "'Roboto Mono', Consolas, monospace",
    overflowX: 'auto',
    whiteSpace: 'pre',
    wordBreak: 'normal',
    border: `1px solid ${isDark ? '#262D3D' : '#1E293B'}`,
    '& code': {
      backgroundColor: 'transparent',
      color: 'inherit',
      p: 0,
      fontSize: 'inherit',
      fontFamily: 'inherit',
    },
  }

  const inlineCodeSx = {
    backgroundColor: isDark ? 'rgba(255, 255, 255, 0.08)' : '#F1F5F9',
    color: isDark ? '#F1F5F9' : '#0A0A0A',
    borderRadius: '4px',
    px: 0.6,
    py: 0.15,
    fontSize: '0.84em',
    fontFamily: "'Roboto Mono', Consolas, monospace",
    border: `1px solid ${isDark ? 'rgba(255, 255, 255, 0.1)' : '#E2E8F0'}`,
  }

  return (
    <Typography
      component="div"
      variant="body1"
      sx={{
        color: isDark ? '#F1F5F9' : '#0A0A0A',
        lineHeight: 1.65,
        wordBreak: 'break-word',
        fontSize: '0.9375rem',
        '& > *:first-of-type': { mt: 0 },
        '& > *:last-child': { mb: 0 },
        '& p': { mt: 0.25, mb: 0.8 },
        '& h1, & h2, & h3, & h4, & h5, & h6': {
          fontFamily: "Georgia, 'Times New Roman', Cambria, serif",
          color: isDark ? '#FFFFFF' : '#0A0A0A',
          fontWeight: 700,
          lineHeight: 1.3,
          mb: 0.5,
          mt: 1.25,
        },
        '& h1': { fontSize: '1.25rem' },
        '& h2': { fontSize: '1.125rem' },
        '& h3': { fontSize: '1.05rem' },
        '& h4, & h5, & h6': { fontSize: '0.975rem' },
        '& ul, & ol': { mt: 0.25, mb: 0.8, pl: 3 },
        '& li': { mb: 0.25 },
        '& blockquote': {
          ml: 0,
          pl: 1.5,
          borderLeft: '3px solid #FF6B00',
          color: textSecondary,
          my: 0.75,
        },
        '& hr': { border: 'none', borderTop: `1px solid ${isDark ? '#262D3D' : '#EAECEF'}`, my: 1.25 },
        '& table': { borderCollapse: 'collapse', mb: 0.75, fontSize: '0.85rem' },
        '& th, & td': { border: `1px solid ${isDark ? '#262D3D' : '#EAECEF'}`, px: 1, py: 0.5 },
        '& th': { backgroundColor: isDark ? '#161922' : '#F8FAFC', fontWeight: 700 },
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={(url) => {
          const safe = /^(https?:|mailto:|#|\/)/i
          if (safe.test(url)) return url
          return ''
        }}
        components={{
          a: ({ href, node, children, ...props }) =>
            href ? (
              <Link
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                underline="hover"
                sx={{ color: '#0284C7', fontWeight: 600 }}
                {...props}
              >
                {children}
              </Link>
            ) : (
              <span {...props}>{children}</span>
            ),
          pre: ({ children }) => <Box component="pre" sx={codeBlockSx}>{children}</Box>,
          code: ({ className, children }) =>
            className ? (
              <code className={className}>{children}</code>
            ) : (
              <Box component="code" sx={inlineCodeSx}>{children}</Box>
            ),
        }}
      >
        {children}
      </ReactMarkdown>
    </Typography>
  )
}

function RagMessageBubble({ message }) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false)

  const { role, text, sources, diagnostics, streaming, error } = message || {}
  const isUser = role === 'user'
  const hasSources = Array.isArray(sources) && sources.length > 0
  const hasDiagnostics = Boolean(diagnostics) && Object.keys(diagnostics).length > 0
  const abstained = Boolean(diagnostics?.insufficient_evidence)

  // ── User question bubble ────────────────────────────────────────────────
  if (isUser) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', width: '100%' }}>
        <Box
          sx={{
            maxWidth: '75%',
            px: 2.2,
            py: 1.4,
            borderRadius: '14px 14px 4px 14px',
            backgroundColor: isDark ? '#1A1E29' : '#0A0A0A',
            color: '#FFFFFF',
            border: isDark ? '1px solid #2B3245' : '1px solid #1A1A1A',
          }}
        >
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5, fontSize: '0.92rem' }}>
            {text}
          </Typography>
        </Box>
      </Box>
    )
  }

  // ── Assistant answer bubble ─────────────────────────────────────────────
  return (
    <Box sx={{ display: 'flex', justifyContent: 'flex-start', width: '100%' }}>
      <Box
        sx={{
          maxWidth: '85%',
          width: '100%',
          px: 2.5,
          py: 2,
          borderRadius: '14px 14px 14px 4px',
          border: `1px solid ${theme.palette.divider}`,
          backgroundColor: theme.palette.background.paper,
        }}
      >
        {error ? (
          <Alert severity="error" sx={{ borderRadius: '8px' }}>
            {error}
          </Alert>
        ) : abstained ? (
          <Alert severity="info" sx={{ borderRadius: '8px' }}>
            I couldn't find enough evidence in the selected documents to answer that question confidently.
          </Alert>
        ) : (
          <>
            <MarkdownContent isDark={isDark} textSecondary={theme.palette.text.secondary}>
              {sanitizeCitations(text, sources)}
            </MarkdownContent>
            {streaming && text && (
              <Typography component="span" sx={{ color: '#FF6B00', ml: 0.5, fontWeight: 700 }}>
                ▌
              </Typography>
            )}

            {/* Streaming state with no tokens yet */}
            {streaming && !text && (
              <Typography variant="body2" sx={{ color: theme.palette.text.secondary }}>
                Synthesizing answer from selected documents…
              </Typography>
            )}
          </>
        )}

        {/* Collapsible citations */}
        {hasSources && (
          <Box sx={{ mt: 2 }}>
            <Divider sx={{ mb: 1.2, borderColor: theme.palette.divider }} />
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <Typography
                variant="overline"
                sx={{
                  color: theme.palette.text.secondary,
                  letterSpacing: '0.04em',
                  fontWeight: 700,
                  fontSize: '0.72rem',
                }}
              >
                Sources & Citations ({sources.length})
              </Typography>
              <IconButton
                size="small"
                onClick={() => setSourcesOpen((prev) => !prev)}
                aria-expanded={sourcesOpen}
                aria-label="Toggle sources"
                sx={{ color: theme.palette.text.secondary }}
              >
                <ExpandMoreIcon
                  fontSize="small"
                  sx={{
                    transform: sourcesOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s',
                  }}
                />
              </IconButton>
            </Box>
            <Collapse in={sourcesOpen} timeout="auto" unmountOnExit>
              <Stack spacing={0.75} sx={{ mt: 0.75 }}>
                {sources.map((source, idx) => (
                  <Tooltip key={source.chunk_id || idx} title={source.chunk_id || ''} arrow>
                    <Chip
                      size="small"
                      icon={<ChatBubbleOutlineOutlinedIcon sx={{ fontSize: '14px !important' }} />}
                      label={`[${idx + 1}] ${source.filename}${formatPages(source) ? ` · ${formatPages(source)}` : ''}`}
                      variant="outlined"
                      sx={{
                        justifyContent: 'flex-start',
                        borderColor: theme.palette.divider,
                        backgroundColor: isDark ? '#141720' : '#F8FAFC',
                        '& .MuiChip-label': {
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          color: isDark ? '#F1F5F9' : '#0A0A0A',
                        },
                        '& .MuiChip-icon': { color: '#0284C7' },
                      }}
                    />
                  </Tooltip>
                ))}
              </Stack>
            </Collapse>
          </Box>
        )}

        {/* Developer diagnostics expander */}
        {hasDiagnostics && (
          <Box sx={{ mt: 1.5 }}>
            <Divider sx={{ mb: 1, borderColor: theme.palette.divider }} />
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <Typography
                variant="overline"
                sx={{ color: theme.palette.text.secondary, letterSpacing: '0.04em', fontSize: '0.68rem' }}
              >
                Developer Diagnostics
              </Typography>
              <IconButton
                size="small"
                onClick={() => setDiagnosticsOpen((prev) => !prev)}
                aria-expanded={diagnosticsOpen}
                aria-label="Toggle developer diagnostics"
                sx={{ color: theme.palette.text.secondary }}
              >
                <ExpandMoreIcon
                  fontSize="small"
                  sx={{
                    transform: diagnosticsOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s',
                  }}
                />
              </IconButton>
            </Box>
            <Collapse in={diagnosticsOpen} timeout="auto" unmountOnExit>
              <Box
                component="pre"
                sx={{
                  mt: 1,
                  p: 1.25,
                  borderRadius: '8px',
                  backgroundColor: isDark ? '#0C0E14' : '#F8FAFC',
                  border: `1px solid ${theme.palette.divider}`,
                  fontSize: '0.75rem',
                  color: theme.palette.text.secondary,
                  fontFamily: "'Roboto Mono', Consolas, monospace",
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  m: 0,
                }}
              >
                {JSON.stringify(diagnostics, null, 2)}
              </Box>
            </Collapse>
          </Box>
        )}
      </Box>
    </Box>
  )
}

export default React.memo(RagMessageBubble)
