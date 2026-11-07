import React, { useState, useRef } from 'react'
import {
  TableRow,
  TableCell,
  Box,
  Typography,
  Chip,
  IconButton,
  Tooltip,
  Checkbox,
  Menu,
  MenuItem,
  ListItemIcon,
  Divider,
  useTheme,
} from '@mui/material'
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf'
import DescriptionIcon from '@mui/icons-material/Description'
import TextSnippetIcon from '@mui/icons-material/TextSnippet'
import CodeIcon from '@mui/icons-material/Code'
import InsertDriveFileIcon from '@mui/icons-material/InsertDriveFile'
import VisibilityIcon from '@mui/icons-material/Visibility'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import MoreVertIcon from '@mui/icons-material/MoreVert'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'

function getMuiFileTypeIcon(contentType, filename) {
  const name = (filename || '').toLowerCase()
  if (contentType === 'application/pdf' || name.endsWith('.pdf')) {
    return <PictureAsPdfIcon sx={{ color: '#DC2626', fontSize: 24 }} />
  }
  if (name.endsWith('.docx') || contentType?.includes('wordprocessingml')) {
    return <DescriptionIcon sx={{ color: '#0284C7', fontSize: 24 }} />
  }
  if (contentType === 'text/markdown' || name.endsWith('.md')) {
    return <CodeIcon sx={{ color: '#FF6B00', fontSize: 24 }} />
  }
  if (contentType === 'text/plain' || name.endsWith('.txt')) {
    return <TextSnippetIcon sx={{ color: '#16A34A', fontSize: 24 }} />
  }
  return <InsertDriveFileIcon sx={{ color: '#64748B', fontSize: 24 }} />
}

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function FileRow({
  doc,
  selected,
  onToggleSelect,
  onOpen,
  onEdit,
  onDelete,
  onAddToKnowledgeBase,
  selectionMode,
  onLongPress,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const parsedTags = doc.tags ? doc.tags.split(',').map((t) => t.trim()).filter(Boolean) : []
  const [anchorEl, setAnchorEl] = useState(null)
  const menuOpen = Boolean(anchorEl)
  const longPressTimerRef = useRef(null)
  const longPressFiredRef = useRef(false)

  const handleMenuOpen = (e) => setAnchorEl(e.currentTarget)
  const handleMenuClose = () => setAnchorEl(null)

  const runMenuAction = (fn) => {
    handleMenuClose()
    fn(doc)
  }

  const handleAddToKb = () => {
    handleMenuClose()
    if (typeof onAddToKnowledgeBase === 'function') onAddToKnowledgeBase(doc)
  }

  const clearLongPress = () => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current)
      longPressTimerRef.current = null
    }
  }

  const handlePointerDown = (e) => {
    if (e.button !== 0) return
    if (e.target.closest('button')) return
    longPressFiredRef.current = false
    longPressTimerRef.current = setTimeout(() => {
      longPressFiredRef.current = true
      if (typeof onLongPress === 'function') onLongPress(doc.fileId)
    }, 500)
  }

  const handlePointerUp = () => {
    clearLongPress()
  }

  const handlePointerLeave = () => {
    clearLongPress()
  }

  const handleRowClick = () => {
    if (longPressFiredRef.current) {
      longPressFiredRef.current = false
      return
    }
    if (selectionMode && typeof onToggleSelect === 'function') {
      onToggleSelect(doc.fileId)
    }
  }

  return (
    <TableRow
      hover
      selected={Boolean(selected)}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerLeave}
      onPointerCancel={handlePointerLeave}
      onClick={handleRowClick}
      sx={{
        height: 72,
        transition: 'background-color 0.15s ease',
        cursor: selectionMode ? 'pointer' : 'default',
        '&:hover': {
          backgroundColor: isDark ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.02)',
        },
        '& td': {
          borderColor: theme.palette.divider,
          py: 1,
          verticalAlign: 'middle',
        },
      }}
    >
      {selectionMode && (
        <TableCell padding="checkbox" sx={{ width: 48 }}>
          <Checkbox
            size="small"
            checked={Boolean(selected)}
            onChange={() => onToggleSelect && onToggleSelect(doc.fileId)}
            onClick={(e) => e.stopPropagation()}
            inputProps={{ 'aria-label': `Select ${doc.filename}` }}
            sx={{
              color: theme.palette.text.secondary,
              '&.Mui-checked': { color: '#FF6B00' }, // Orange highlight
            }}
          />
        </TableCell>
      )}

      {/* File Icon & Name */}
      <TableCell sx={{ overflow: 'hidden' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, overflow: 'hidden' }}>
          <Box sx={{ flexShrink: 0, display: 'flex', alignItems: 'center' }}>
            {getMuiFileTypeIcon(doc.contentType, doc.filename)}
          </Box>
          <Box sx={{ overflow: 'hidden', minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, overflow: 'hidden' }}>
              <Typography
                variant="subtitle2"
                sx={{
                  fontWeight: 700,
                  color: isDark ? '#F1F5F9' : '#0A0A0A',
                  lineHeight: 1.25,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {doc.title || doc.filename}
              </Typography>
              {(() => {
                const status = (
                  doc.indexingStatus ||
                  doc.indexing_status ||
                  (doc.isIndexed ? 'indexed' : 'pending')
                ).toLowerCase()
                if (status === 'indexed') {
                  return (
                    <Chip
                      label="Indexed"
                      size="small"
                      variant="outlined"
                      sx={{
                        height: 18,
                        fontSize: '0.62rem',
                        fontWeight: 700,
                        borderColor: isDark ? 'rgba(34, 197, 94, 0.4)' : '#86EFAC',
                        color: isDark ? '#86EFAC' : '#166534',
                        backgroundColor: isDark ? 'rgba(34, 197, 94, 0.12)' : '#F0FDF4',
                        borderRadius: '4px',
                        px: 0.5,
                        flexShrink: 0,
                      }}
                    />
                  )
                }
                if (status === 'processing') {
                  return (
                    <Chip
                      label="Indexing..."
                      size="small"
                      variant="outlined"
                      sx={{
                        height: 18,
                        fontSize: '0.62rem',
                        fontWeight: 700,
                        borderColor: isDark ? 'rgba(255, 107, 0, 0.4)' : '#FFD8BF',
                        color: '#FF6B00',
                        backgroundColor: isDark ? 'rgba(255, 107, 0, 0.12)' : '#FFF5EE',
                        borderRadius: '4px',
                        px: 0.5,
                        flexShrink: 0,
                      }}
                    />
                  )
                }
                if (status === 'failed') {
                  return (
                    <Tooltip
                      title={doc.lastError || doc.last_error || 'Vector indexing failed during background process.'}
                      arrow
                    >
                      <Chip
                        label="Failed"
                        size="small"
                        variant="outlined"
                        sx={{
                          height: 18,
                          fontSize: '0.62rem',
                          fontWeight: 700,
                          borderColor: isDark ? 'rgba(239, 68, 68, 0.4)' : '#FECACA',
                          color: isDark ? '#FCA5A5' : '#991B1B',
                          backgroundColor: isDark ? 'rgba(239, 68, 68, 0.12)' : '#FEF2F2',
                          borderRadius: '4px',
                          px: 0.5,
                          flexShrink: 0,
                          cursor: 'pointer',
                        }}
                      />
                    </Tooltip>
                  )
                }
                return (
                  <Chip
                    label="Pending"
                    size="small"
                    variant="outlined"
                    sx={{
                      height: 18,
                      fontSize: '0.62rem',
                      fontWeight: 700,
                      borderColor: theme.palette.divider,
                      color: theme.palette.text.secondary,
                      backgroundColor: isDark ? '#141720' : '#F8FAFC',
                      borderRadius: '4px',
                      px: 0.5,
                      flexShrink: 0,
                    }}
                  />
                )
              })()}
              {doc.score !== undefined && doc.score !== null && (
                <Chip
                  label={`🎯 ${(doc.score * 100).toFixed(0)}% Match`}
                  size="small"
                  variant="outlined"
                  sx={{
                    height: 18,
                    fontSize: '0.62rem',
                    fontWeight: 700,
                    borderColor: isDark ? 'rgba(2, 132, 199, 0.4)' : '#BAE6FD',
                    color: '#0284C7', // Water Blue
                    backgroundColor: isDark ? 'rgba(2, 132, 199, 0.12)' : '#F0F9FF',
                    borderRadius: '4px',
                    px: 0.5,
                    flexShrink: 0,
                  }}
                />
              )}
            </Box>
            <Typography
              variant="caption"
              sx={{
                color: theme.palette.text.secondary,
                display: 'block',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {doc.filename} &bull; {formatFileSize(doc.sizeBytes)}
            </Typography>
          </Box>
        </Box>
      </TableCell>

      {/* Description & Tags */}
      <TableCell sx={{ overflow: 'hidden' }}>
        <Typography
          variant="body2"
          sx={{
            color: doc.description ? (isDark ? '#CBD5E1' : '#334155') : theme.palette.text.secondary,
            fontStyle: doc.description ? 'normal' : 'italic',
            fontSize: '0.82rem',
            lineHeight: 1.3,
            maxHeight: '2.6em',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            wordBreak: 'break-word',
            mb: parsedTags.length > 0 ? 0.4 : 0,
          }}
        >
          {doc.description || 'No description provided.'}
        </Typography>
        {parsedTags.length > 0 && (
          <Box
            sx={{
              display: 'flex',
              gap: 0.5,
              flexWrap: 'nowrap',
              overflowX: 'auto',
              msOverflowStyle: 'none',
              scrollbarWidth: 'none',
              '&::-webkit-scrollbar': { display: 'none' },
            }}
          >
            {parsedTags.map((tag) => (
              <Chip
                key={tag}
                label={tag}
                size="small"
                variant="outlined"
                sx={{
                  height: 18,
                  fontSize: '0.68rem',
                  fontWeight: 600,
                  borderRadius: '4px',
                  borderColor: theme.palette.divider,
                  color: theme.palette.text.secondary,
                  backgroundColor: isDark ? '#141720' : '#F1F5F9',
                  flexShrink: 0,
                }}
              />
            ))}
          </Box>
        )}
      </TableCell>

      {/* Overflow menu */}
      <TableCell align="right" sx={{ width: 56, minWidth: 56, pr: 1 }}>
        <IconButton
          size="small"
          aria-label={`Actions for ${doc.filename}`}
          aria-controls={menuOpen ? `row-menu-${doc.fileId}` : undefined}
          aria-haspopup="true"
          aria-expanded={menuOpen ? 'true' : undefined}
          onClick={(e) => {
            e.stopPropagation()
            handleMenuOpen(e)
          }}
          sx={{
            color: theme.palette.text.secondary,
            '&:hover': {
              backgroundColor: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.04)',
              color: isDark ? '#FFFFFF' : '#0A0A0A',
            },
          }}
        >
          <MoreVertIcon fontSize="small" />
        </IconButton>
        <Menu
          id={`row-menu-${doc.fileId}`}
          anchorEl={anchorEl}
          open={menuOpen}
          onClose={handleMenuClose}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
          transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          slotProps={{
            paper: {
              sx: {
                borderRadius: '10px',
                border: `1px solid ${theme.palette.divider}`,
                mt: 0.5,
                minWidth: 210,
                backgroundColor: theme.palette.background.paper,
                boxShadow: isDark
                  ? '0 10px 25px -5px rgba(0, 0, 0, 0.6)'
                  : '0 10px 25px -5px rgba(0, 0, 0, 0.08)',
              },
            },
          }}
        >
          <MenuItem
            onClick={() => {
              handleMenuClose()
              onOpen(doc.s3Key)
            }}
            sx={{ py: 1 }}
          >
            <ListItemIcon>
              <VisibilityIcon fontSize="small" sx={{ color: '#0284C7' }} />
            </ListItemIcon>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>Open File</Typography>
          </MenuItem>
          <MenuItem onClick={() => runMenuAction(onEdit)} sx={{ py: 1 }}>
            <ListItemIcon>
              <EditIcon fontSize="small" sx={{ color: theme.palette.text.secondary }} />
            </ListItemIcon>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>Edit Metadata</Typography>
          </MenuItem>
          <MenuItem onClick={handleAddToKb} sx={{ py: 1 }}>
            <ListItemIcon>
              <AutoAwesomeIcon fontSize="small" sx={{ color: '#FF6B00' }} />
            </ListItemIcon>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>Add to Knowledge Base</Typography>
          </MenuItem>
          <Divider sx={{ my: 0.5, borderColor: theme.palette.divider }} />
          <MenuItem onClick={() => runMenuAction(onDelete)} sx={{ color: '#DC2626', py: 1 }}>
            <ListItemIcon>
              <DeleteIcon fontSize="small" sx={{ color: '#DC2626' }} />
            </ListItemIcon>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>Delete</Typography>
          </MenuItem>
        </Menu>
      </TableCell>
    </TableRow>
  )
}

export default React.memo(FileRow)
