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
  Skeleton
} from '@mui/material'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import FileRow from './FileRow'

export default function FileList({
  documents,
  loadingDocs,
  searchTerm,
  onOpen,
  onEdit,
  onDelete
}) {
  // Filter documents based on search term
  const filteredDocs = documents.filter((doc) => {
    if (!searchTerm.trim()) return true
    const term = searchTerm.toLowerCase()
    const titleMatch = doc.title?.toLowerCase().includes(term)
    const filenameMatch = doc.filename?.toLowerCase().includes(term)
    const descMatch = doc.description?.toLowerCase().includes(term)
    const tagMatch = doc.tags?.toLowerCase().includes(term)
    return titleMatch || filenameMatch || descMatch || tagMatch
  })

  return (
    <TableContainer
      component={Paper}
      elevation={0}
      sx={{
        borderRadius: '12px',
        border: '1px solid #E2E8F0',
        backgroundColor: '#FFFFFF',
        overflow: 'hidden'
      }}
    >
      <Table sx={{ minWidth: 650, tableLayout: 'fixed' }}>
        <TableHead sx={{ backgroundColor: '#F8FAFC' }}>
          <TableRow sx={{ '& th': { borderColor: '#E2E8F0', color: '#64748B', fontWeight: 700, fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.05em' } }}>
            <TableCell sx={{ width: '32%' }}>Document / Format</TableCell>
            <TableCell sx={{ width: '48%' }}>Metadata & Tags</TableCell>
            <TableCell align="right" sx={{ width: '130px' }}>Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {loadingDocs ? (
            // Skeleton Loading State
            Array.from({ length: 4 }).map((_, index) => (
              <TableRow key={index} sx={{ '& td': { borderColor: '#E2E8F0', py: 2.5 } }}>
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
                  <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 1 }}>
                    <Skeleton variant="circular" width={28} height={28} />
                    <Skeleton variant="circular" width={28} height={28} />
                    <Skeleton variant="circular" width={28} height={28} />
                  </Box>
                </TableCell>
              </TableRow>
            ))
          ) : filteredDocs.length === 0 ? (
            // Empty State View
            <TableRow>
              <TableCell colSpan={3} sx={{ borderBottom: 'none', py: 8 }}>
                <Box
                  sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    textAlign: 'center',
                    gap: 1.5
                  }}
                >
                  <FolderOpenIcon sx={{ fontSize: 48, color: '#94A3B8' }} />
                  <Typography variant="h6" sx={{ color: '#0F172A', fontWeight: 700, fontSize: '1rem' }}>
                    {searchTerm ? 'No matching documents found' : 'No documents found in vault'}
                  </Typography>
                  <Typography variant="body2" sx={{ color: '#64748B', maxWidth: 400 }}>
                    {searchTerm
                      ? `No files match "${searchTerm}". Try a different search term.`
                      : 'Upload a text, markdown, PDF, or Word document using the upload button to get started.'}
                  </Typography>
                </Box>
              </TableCell>
            </TableRow>
          ) : (
            // Document List Rows
            filteredDocs.map((doc) => (
              <FileRow
                key={doc.fileId}
                doc={doc}
                onOpen={onOpen}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))
          )}
        </TableBody>
      </Table>
    </TableContainer>
  )
}
