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
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ChatBubbleOutlineOutlinedIcon from '@mui/icons-material/ChatBubbleOutlineOutlined'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * frontend/src/components/RagMessageBubble.jsx
 *
 * Phase 8 §5.4 chat bubble. Renders one conversation message:
 *   - user message: right-aligned question pill
 *   - assistant message: live answer text (pre-wrap), collapsible citations
 *     from `sources`, and a "Developer diagnostics" expander that is only
 *     visible in the debug flow (never part of the normal answer).
 *
 * Purely presentational: no network, no business logic. Collapse open/close is
 * local view state. All styling is MUI via the sx prop + theme tokens.
 */

function formatPages(source) {
  if (source.page_start == null) return ''
  return source.page_start === source.page_end
    ? `Page ${source.page_start}`
    : `Pages ${source.page_start}–${source.page_end}`
}

// Citation sanitizer: replaces raw [id=<uuid>] tokens the model emits with
// human-safe numbered refs [1], [2] that map to the expandable Sources list.
// Unknown ids are stripped. No secret (chunk uuid) ever reaches the UI.
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
  // Collapse artefacts like "  " or " .", " ," left after stripping unknown ids
  out = out.replace(/\[\s*\]/g, '').replace(/ {2,}/g, ' ')
  return out
}

const codeBlockSx = {
  mt: 1,
  mb: 1,
  p: 1.25,
  borderRadius: '8px',
  backgroundColor: '#0F172A',
  color: '#E2E8F0',
  fontSize: '0.8125rem',
  fontFamily: "'Roboto Mono', Consolas, monospace",
  overflowX: 'auto',
  whiteSpace: 'pre',
  wordBreak: 'normal',
  '& code': {
    backgroundColor: 'transparent',
    color: 'inherit',
    p: 0,
    fontSize: 'inherit',
    fontFamily: 'inherit',
  },
}

const inlineCodeSx = {
  backgroundColor: '#EEF2F7',
  color: '#0A192F',
  borderRadius: '4px',
  px: 0.5,
  py: 0.1,
  fontSize: '0.82em',
  fontFamily: "'Roboto Mono', Consolas, monospace",
}

function MarkdownContent({ children }) {
  return (
    <Typography
      component="div"
      variant="body1"
      sx={{
        color: '#0F172A',
        lineHeight: 1.6,
        wordBreak: 'break-word',
        fontSize: '0.9375rem',
        '& > *:first-of-type': { mt: 0 },
        '& > *:last-child': { mb: 0 },
        '& p': { mt: 0.25, mb: 0.75 },
        '& h1, & h2, & h3, & h4, & h5, & h6': {
          color: '#0A192F',
          fontWeight: 800,
          lineHeight: 1.3,
          mb: 0.5,
          mt: 1.25,
        },
        '& h1': { fontSize: '1.25rem' },
        '& h2': { fontSize: '1.125rem' },
        '& h3': { fontSize: '1.05rem' },
        '& h4, & h5, & h6': { fontSize: '0.975rem' },
        '& ul, & ol': { mt: 0.25, mb: 0.75, pl: 3 },
        '& li': { mb: 0.25 },
        '& blockquote': {
          ml: 0,
          pl: 1.5,
          borderLeft: '3px solid #E2E8F0',
          color: '#475569',
          my: 0.75,
        },
        '& hr': { border: 'none', borderTop: '1px solid #E2E8F0', my: 1.25 },
        '& table': { borderCollapse: 'collapse', mb: 0.75, fontSize: '0.85rem' },
        '& th, & td': { border: '1px solid #E2E8F0', px: 1, py: 0.5 },
        '& th': { backgroundColor: '#F8FAFC', fontWeight: 700 },
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
                color="primary"
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
            px: 2,
            py: 1.25,
            borderRadius: '12px 12px 4px 12px',
            backgroundColor: '#0A192F',
            color: '#FFFFFF',
          }}
        >
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5 }}>
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
          px: 2,
          py: 1.5,
          borderRadius: '12px 12px 12px 4px',
          border: '1px solid #E2E8F0',
          backgroundColor: '#FFFFFF',
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
            <MarkdownContent>{sanitizeCitations(text, sources)}</MarkdownContent>
            {streaming && text && (
              <Typography component="span" sx={{ color: '#0A192F', ml: 0.5 }}>
                ▌
              </Typography>
            )}

            {/* Streaming state with no tokens yet */}
            {streaming && !text && (
              <Typography variant="body2" sx={{ color: '#64748B' }}>
                Thinking…
              </Typography>
            )}
          </>
        )}

        {/* Collapsible citations */}
        {hasSources && (
          <Box sx={{ mt: 1.5 }}>
            <Divider sx={{ mb: 1 }} />
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <Typography variant="overline" sx={{ color: '#64748B', letterSpacing: '0.04em' }}>
                Sources ({sources.length})
              </Typography>
              <IconButton
                size="small"
                onClick={() => setSourcesOpen((prev) => !prev)}
                aria-expanded={sourcesOpen}
                aria-label="Toggle sources"
                sx={{ color: '#64748B' }}
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
                      icon={<ChatBubbleOutlineOutlinedIcon />}
                      label={`${source.filename}${formatPages(source) ? ` · ${formatPages(source)}` : ''}`}
                      variant="outlined"
                      sx={{
                        justifyContent: 'flex-start',
                        '& .MuiChip-label': {
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          color: '#0F172A',
                        },
                        '& .MuiChip-icon': { color: '#64748B' },
                      }}
                    />
                  </Tooltip>
                ))}
              </Stack>
            </Collapse>
          </Box>
        )}

        {/* Developer diagnostics expander (gated, never in normal answer flow) */}
        {hasDiagnostics && (
          <Box sx={{ mt: 1.5 }}>
            <Divider sx={{ mb: 1 }} />
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <Typography variant="overline" sx={{ color: '#94A3B8', letterSpacing: '0.04em' }}>
                Developer diagnostics
              </Typography>
              <IconButton
                size="small"
                onClick={() => setDiagnosticsOpen((prev) => !prev)}
                aria-expanded={diagnosticsOpen}
                aria-label="Toggle developer diagnostics"
                sx={{ color: '#94A3B8' }}
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
                  backgroundColor: '#F8FAFC',
                  border: '1px solid #E2E8F0',
                  fontSize: '0.75rem',
                  color: '#334155',
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