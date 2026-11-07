import React from 'react'
import {
  TableContainer,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  Paper,
  Box,
  Typography,
  Skeleton,
  TablePagination,
  useTheme,
} from '@mui/material'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import FileRow from './FileRow'

function FileList({
  documents,
  loadingDocs,
  searchTerm,
  onOpen,
  onEdit,
  onDelete,
  onAddToKnowledgeBase,
  selectedIds,
  onToggleSelect,
  selectionMode = false,
  onLongPress,
  page = 0,
  rowsPerPage = 50,
  totalCount = 0,
  onPageChange,
  onRowsPerPageChange,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const displayedDocs = documents || []
  const colSpan = selectionMode ? 4 : 3

  return (
    <TableContainer
      component={Paper}
      elevation={0}
      sx={{
        borderRadius: '12px',
        border: `1px solid ${theme.palette.divider}`,
        backgroundColor: theme.palette.background.paper,
        overflow: 'hidden',
      }}
    >
      <Table sx={{ minWidth: 650, tableLayout: 'fixed' }}>
        <TableHead sx={{ backgroundColor: isDark ? '#141720' : '#F8FAFC' }}>
          <TableRow
            sx={{
              '& th': {
                borderColor: theme.palette.divider,
                color: theme.palette.text.secondary,
                fontWeight: 700,
                fontSize: '0.75rem',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              },
            }}
          >
            {selectionMode && <TableCell padding="checkbox" sx={{ width: 48 }} />}
            <TableCell sx={{ width: '34%' }}>Document / Format</TableCell>
            <TableCell sx={{ width: '46%' }}>Metadata & Tags</TableCell>
            <TableCell align="right" sx={{ width: 56 }} />
          </TableRow>
        </TableHead>
        <TableBody>
          {loadingDocs ? (
            Array.from({ length: 4 }).map((_, index) => (
              <TableRow key={index} sx={{ '& td': { borderColor: theme.palette.divider, py: 2.5 } }}>
                {selectionMode && (
                  <TableCell padding="checkbox">
                    <Skeleton variant="circular" width={20} height={20} sx={{ mx: 'auto' }} />
                  </TableCell>
                )}
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <Skeleton variant="circular" width={28} height={28} />
                    <Box sx={{ flexGrow: 1 }}>
                      <Skeleton variant="text" width="60%" height={20} />
                      <Skeleton variant="text" width="40%" height={16} />
                    </Box>
                  </Box>
                </TableCell>
                <TableCell>
                  <Skeleton variant="text" width="80%" height={20} />
                  <Skeleton variant="text" width="30%" height={16} />
                </TableCell>
                <TableCell align="right">
                  <Skeleton variant="circular" width={28} height={28} sx={{ ml: 'auto' }} />
                </TableCell>
              </TableRow>
            ))
          ) : displayedDocs.length === 0 ? (
            <TableRow>
              <TableCell colSpan={colSpan} sx={{ borderBottom: 'none', py: 8 }}>
                <Box
                  sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    textAlign: 'center',
                    gap: 1.5,
                  }}
                >
                  <FolderOpenIcon sx={{ fontSize: 44, color: theme.palette.text.secondary }} />
                  <Typography
                    variant="h6"
                    sx={{
                      color: isDark ? '#F1F5F9' : '#0A0A0A',
                      fontWeight: 700,
                      fontSize: '1rem',
                    }}
                  >
                    {searchTerm ? 'No matching documents found' : 'No documents in your Swan Drive vault'}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ color: theme.palette.text.secondary, maxWidth: 420, lineHeight: 1.5 }}
                  >
                    {searchTerm
                      ? `No files match "${searchTerm}". Try a different keyword or semantic query.`
                      : 'Upload a PDF, Word (docx), Markdown, or text file using the button above to start building your cloud vault.'}
                  </Typography>
                </Box>
              </TableCell>
            </TableRow>
          ) : (
            displayedDocs.map((doc) => (
              <FileRow
                key={doc.fileId}
                doc={doc}
                selected={selectedIds ? selectedIds.has(doc.fileId) : false}
                onToggleSelect={onToggleSelect}
                selectionMode={selectionMode}
                onLongPress={onLongPress}
                onOpen={onOpen}
                onEdit={onEdit}
                onDelete={onDelete}
                onAddToKnowledgeBase={onAddToKnowledgeBase}
              />
            ))
          )}
        </TableBody>
      </Table>
      {onPageChange && totalCount > 0 && (
        <TablePagination
          rowsPerPageOptions={[10, 25, 50, 100]}
          component="div"
          count={totalCount}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={onPageChange}
          onRowsPerPageChange={onRowsPerPageChange}
          sx={{
            borderTop: `1px solid ${theme.palette.divider}`,
            color: theme.palette.text.secondary,
          }}
        />
      )}
    </TableContainer>
  )
}

export default React.memo(FileList)
