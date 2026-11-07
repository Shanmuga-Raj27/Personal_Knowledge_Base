import React from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  useTheme,
} from '@mui/material'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'

export default function DeleteConfirmDialog({
  open,
  onClose,
  docToDelete,
  deleting,
  onConfirmDelete,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  return (
    <Dialog
      open={open}
      onClose={() => !deleting && onClose()}
      fullWidth
      maxWidth="xs"
      slotProps={{
        paper: {
          sx: {
            borderRadius: '14px',
            border: `1px solid ${theme.palette.divider}`,
            backgroundColor: theme.palette.background.paper,
            p: 1,
          },
        },
      }}
    >
      <DialogTitle
        sx={{
          fontFamily: "Georgia, 'Times New Roman', Cambria, serif",
          fontWeight: 700,
          fontSize: '1.2rem',
          color: '#DC2626',
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          pt: 2,
          pb: 1,
        }}
      >
        <WarningAmberIcon sx={{ color: '#DC2626' }} /> Confirm Permanent Deletion
      </DialogTitle>
      <DialogContent sx={{ py: 1.5 }}>
        <Typography
          variant="body2"
          sx={{ mb: 2, color: isDark ? '#F1F5F9' : '#0A0A0A', fontWeight: 600 }}
        >
          Are you sure you want to delete{' '}
          <strong>{docToDelete?.title || docToDelete?.filename}</strong>?
        </Typography>
        <Box
          sx={{
            p: 1.5,
            borderRadius: '8px',
            backgroundColor: isDark ? 'rgba(220, 38, 38, 0.12)' : 'rgba(220, 38, 38, 0.05)',
            border: '1px solid rgba(220, 38, 38, 0.25)',
          }}
        >
          <Typography variant="caption" sx={{ color: '#DC2626', display: 'block', fontWeight: 500 }}>
            This will permanently remove the file from Swan Drive S3 cloud storage and metadata database.
            This action cannot be undone.
          </Typography>
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button
          disabled={deleting}
          onClick={onClose}
          sx={{ color: theme.palette.text.secondary, fontWeight: 600, '&:hover': { color: '#0A0A0A' } }}
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
            px: 2.5,
            '&:hover': { backgroundColor: '#B91C1C', boxShadow: 'none' },
          }}
        >
          {deleting ? 'Deleting...' : 'Delete Document'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
