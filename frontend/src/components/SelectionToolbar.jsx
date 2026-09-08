import { Paper, Typography, IconButton, Button } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'

function SelectionToolbar({ selectedCount, onClear, onAddToKnowledgeBase, disabled }) {
  return (
    <Paper
      elevation={0}
      sx={{
        p: 2,
        mb: 4,
        borderRadius: '12px',
        backgroundColor: '#0A192F',
        border: '1px solid #0A192F',
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
          '&:hover': { backgroundColor: 'rgba(255,255,255,0.12)' },
        }}
      >
        <CloseIcon fontSize="small" />
      </IconButton>

      <Typography sx={{ color: '#FFFFFF', fontWeight: 700, fontSize: '0.9rem', flexGrow: 1 }}>
        {selectedCount} selected
      </Typography>

      <Button
        variant="contained"
        startIcon={<AutoAwesomeIcon />}
        onClick={onAddToKnowledgeBase}
        disabled={Boolean(disabled)}
        sx={{
          backgroundColor: '#FFFFFF',
          color: '#0A192F',
          fontWeight: 700,
          fontSize: '0.85rem',
          textTransform: 'none',
          px: 2.5,
          py: 0.9,
          borderRadius: '8px',
          boxShadow: 'none',
          whiteSpace: 'nowrap',
          '&:hover': { backgroundColor: '#F1F5F9', boxShadow: 'none' },
          '&.Mui-disabled': { backgroundColor: '#E2E8F0', color: '#94A3B8' },
        }}
      >
        Add to Knowledge Base
      </Button>
    </Paper>
  )
}

export default SelectionToolbar
