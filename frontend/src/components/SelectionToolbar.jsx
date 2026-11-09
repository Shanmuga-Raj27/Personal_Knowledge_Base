import React from 'react'
import { Paper, Typography, IconButton, Button, useTheme } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'

function SelectionToolbar({ selectedCount, onClear, onAddToKnowledgeBase, disabled }) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  return (
    <Paper
      elevation={0}
      sx={{
        p: 1.8,
        mb: 3,
        borderRadius: '12px',
        backgroundColor: isDark ? '#161922' : '#0A0A0A',
        border: `1px solid ${isDark ? '#262D3D' : '#1A1A1A'}`,
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
      }}
    >
      <IconButton
        size="small"
        onClick={onClear}
        aria-label="Clear selection"
        sx={{
          color: '#FFFFFF',
          border: '1px solid rgba(255,255,255,0.2)',
          borderRadius: '8px',
          p: 0.75,
          '&:hover': { backgroundColor: 'rgba(255,255,255,0.12)' },
        }}
      >
        <CloseIcon fontSize="small" />
      </IconButton>

      <Typography sx={{ color: '#FFFFFF', fontWeight: 700, fontSize: '0.9rem', flexGrow: 1 }}>
        {selectedCount} document{selectedCount === 1 ? '' : 's'} selected
      </Typography>

      <Button
        variant="contained"
        startIcon={<AutoAwesomeIcon />}
        onClick={onAddToKnowledgeBase}
        disabled={Boolean(disabled)}
        sx={{
          backgroundColor: '#0284C7', // Water Blue
          color: '#FFFFFF',
          fontWeight: 700,
          fontSize: '0.85rem',
          textTransform: 'none',
          px: 2.5,
          py: 0.85,
          borderRadius: '8px',
          boxShadow: 'none',
          whiteSpace: 'nowrap',
          '&:hover': {
            backgroundColor: '#0369A1',
            boxShadow: 'none',
          },
          '&.Mui-disabled': {
            backgroundColor: 'rgba(255,255,255,0.15)',
            color: 'rgba(255,255,255,0.4)',
          },
        }}
      >
        Add to Swan AI
      </Button>
    </Paper>
  )
}

export default React.memo(SelectionToolbar)
