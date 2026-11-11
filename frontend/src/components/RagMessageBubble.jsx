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
  Avatar,
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import PersonOutlinedIcon from '@mui/icons-material/PersonOutlined'
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function formatPages(source) {
  if (source.page_start == null) return ''
  return source.page_start === source.page_end
    ? `Page ${source.page_start}`
    : `Pages ${source.page_start}–${source.page_end}`
}

const CITATION_BRACKET_RE =
  /[\[\(](?:id|chunk_id)=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})[\]\)]/gi
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
  out = out.replace(/[\[\(]\s*[\]\)]/g, '').replace(/ {2,}/g, ' ')
  return out
}

function MarkdownContent({ children, isDark, textSecondary }) {
  const codeBlockSx = {
    mt: 1.25,
    mb: 1.25,
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
        '& table': { borderCollapse: 'collapse', mb: 0.75, fontSize: '0.85rem', width: '100%', overflowX: 'auto', display: 'block' },
        '& th, & td': { border: `1px solid ${isDark ? '#262D3D' : '#EAECEF'}`, px: 1.2, py: 0.6 },
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

  // ── 1. USER MESSAGE (ALIGNED RIGHT) ────────────────────────────────────────────────
  if (isUser) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'flex-end',
          gap: 1.25,
          width: '100%',
        }}
      >
        <Box
          sx={{
            maxWidth: { xs: '85%', sm: '75%' },
            px: 2.2,
            py: 1.35,
            borderRadius: '16px 16px 4px 16px',
            backgroundColor: isDark ? '#1E2433' : '#0284C7', // Water Blue in light mode, deep blue-slate in dark
            color: '#FFFFFF',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.08)',
          }}
        >
          <Typography
            variant="body2"
            sx={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              lineHeight: 1.55,
              fontSize: '0.925rem',
              fontWeight: 500,
            }}
          >
            {text}
          </Typography>
        </Box>
        <Avatar
          sx={{
            width: 32,
            height: 32,
            backgroundColor: isDark ? '#262D3D' : '#E2E8F0',
            color: isDark ? '#94A3B8' : '#475569',
            fontSize: '0.85rem',
            flexShrink: 0,
            display: { xs: 'none', sm: 'flex' },
          }}
        >
          <PersonOutlinedIcon sx={{ fontSize: 18 }} />
        </Avatar>
      </Box>
    )
  }

  // ── 2. SWAN AI MESSAGE (ALIGNED LEFT) ─────────────────────────────────────────────
  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'flex-start',
        alignItems: 'flex-start',
        gap: 1.5,
        width: '100%',
      }}
    >
      {/* Swan AI Avatar Badge */}
      <Avatar
        sx={{
          width: 34,
          height: 34,
          backgroundColor: isDark ? 'rgba(255, 107, 0, 0.18)' : '#FFF5EE',
          border: `1px solid ${isDark ? 'rgba(255, 107, 0, 0.35)' : '#FFD8BF'}`,
          color: '#FF6B00',
          flexShrink: 0,
          mt: 0.5,
        }}
      >
        <AutoAwesomeIcon sx={{ fontSize: 18 }} />
      </Avatar>

      {/* Message Content Container */}
      <Box
        sx={{
          maxWidth: { xs: '90%', sm: '82%' },
          width: '100%',
          px: 2.5,
          py: 2,
          borderRadius: '4px 16px 16px 16px',
          border: `1px solid ${theme.palette.divider}`,
          backgroundColor: isDark ? '#12151D' : '#FFFFFF',
          boxShadow: isDark
            ? '0 2px 8px rgba(0, 0, 0, 0.3)'
            : '0 2px 8px rgba(0, 0, 0, 0.04)',
        }}
      >
        {error ? (
          <Alert severity="error" sx={{ borderRadius: '8px', py: 0.5 }}>
            {error}
          </Alert>
        ) : abstained ? (
          <Alert severity="info" sx={{ borderRadius: '8px', py: 0.5 }}>
            I couldn't find enough evidence in the selected documents to answer that question confidently.
          </Alert>
        ) : (
          <>
            {/* If streaming and no text yet: Animated pulsing thinking dots */}
            {streaming && !text ? (
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  py: 0.5,
                }}
              >
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.6,
                  }}
                >
                  <Box
                    sx={{
                      width: 7,
                      height: 7,
                      borderRadius: '50%',
                      backgroundColor: '#FF6B00',
                      animation: 'swanPulse 1.2s infinite ease-in-out both',
                      '@keyframes swanPulse': {
                        '0%, 80%, 100%': { transform: 'scale(0.6)', opacity: 0.4 },
                        '40%': { transform: 'scale(1.1)', opacity: 1 },
                      },
                    }}
                  />
                  <Box
                    sx={{
                      width: 7,
                      height: 7,
                      borderRadius: '50%',
                      backgroundColor: '#FF6B00',
                      animation: 'swanPulse 1.2s infinite ease-in-out both 0.2s',
                    }}
                  />
                  <Box
                    sx={{
                      width: 7,
                      height: 7,
                      borderRadius: '50%',
                      backgroundColor: '#FF6B00',
                      animation: 'swanPulse 1.2s infinite ease-in-out both 0.4s',
                    }}
                  />
                </Box>
                <Typography
                  variant="body2"
                  sx={{
                    color: theme.palette.text.secondary,
                    fontStyle: 'italic',
                    fontSize: '0.85rem',
                  }}
                >
                  Swan AI is synthesizing answer from selected documents…
                </Typography>
              </Box>
            ) : (
              <>
                <MarkdownContent isDark={isDark} textSecondary={theme.palette.text.secondary}>
                  {sanitizeCitations(text, sources)}
                </MarkdownContent>
                {streaming && (
                  <Typography
                    component="span"
                    sx={{
                      color: '#FF6B00',
                      ml: 0.5,
                      fontWeight: 700,
                      animation: 'cursorBlink 1s infinite',
                      '@keyframes cursorBlink': {
                        '0%, 100%': { opacity: 1 },
                        '50%': { opacity: 0 },
                      },
                    }}
                  >
                    ▌
                  </Typography>
                )}
              </>
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
                sx={{ color: theme.palette.text.secondary, p: 0.5 }}
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
                      icon={<DescriptionOutlinedIcon sx={{ fontSize: '14px !important' }} />}
                      label={`[${idx + 1}] ${source.filename}${formatPages(source) ? ` · ${formatPages(source)}` : ''}`}
                      variant="outlined"
                      sx={{
                        justifyContent: 'flex-start',
                        borderColor: theme.palette.divider,
                        backgroundColor: isDark ? '#161922' : '#F8FAFC',
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
                Diagnostics
              </Typography>
              <IconButton
                size="small"
                onClick={() => setDiagnosticsOpen((prev) => !prev)}
                aria-expanded={diagnosticsOpen}
                aria-label="Toggle developer diagnostics"
                sx={{ color: theme.palette.text.secondary, p: 0.5 }}
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
                  fontSize: '0.72rem',
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
