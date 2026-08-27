import React from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box
} from '@mui/material'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'

export default function DeleteConfirmDialog({
  open,
  onClose,
  docToDelete,
  deleting,
  onConfirmDelete
}) {
  return (
    <Dialog
      open={open}
      onClose={() => !deleting && onClose()}
      fullWidth
      maxWidth="xs"
      PaperProps={{
        sx: {
          borderRadius: '12px',
          border: '1px solid #E2E8F0',
          backgroundColor: '#FFFFFF',
          p: 1
        }
      }}
    >
      <DialogTitle
        sx={{
          fontWeight: 800,
          fontSize: '1.15rem',
          color: '#DC2626',
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          pt: 2,
          pb: 1
        }}
      >
        <WarningAmberIcon sx={{ color: '#DC2626' }} /> Confirm Permanent Deletion
      </DialogTitle>
      <DialogContent sx={{ py: 1.5 }}>
        <Typography variant="body2" sx={{ mb: 2, color: '#0F172A', fontWeight: 600 }}>
          Are you sure you want to delete <strong>{docToDelete?.title || docToDelete?.filename}</strong>?
        </Typography>
        <Box
          sx={{
            p: 1.5,
            borderRadius: '8px',
            backgroundColor: 'rgba(220, 38, 38, 0.05)',
            border: '1px solid rgba(220, 38, 38, 0.2)'
          }}
        >
          <Typography variant="caption" sx={{ color: '#DC2626', display: 'block', fontWeight: 500 }}>
            This will permanently remove the file from cloud storage and MySQL database. This action cannot be undone.
          </Typography>
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button
          disabled={deleting}
          onClick={onClose}
          sx={{ color: '#64748B', fontWeight: 600, '&:hover': { color: '#0F172A' } }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          disabled={deleting}
          onClick={onConfirmDelete}
          sx={{
            backgroundColor: '#DC2626',
            color: '#FFFFFF',
            fontWeight: 700,
            borderRadius: '8px',
            boxShadow: 'none',
            '&:hover': { backgroundColor: '#B91C1C', boxShadow: 'none' }
          }}
        >
          {deleting ? 'Deleting...' : 'Delete Document'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
