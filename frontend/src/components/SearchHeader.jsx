import React, { useRef } from 'react'
import {
  Box,
  TextField,
  Button,
  InputAdornment,
  Typography,
  LinearProgress,
  IconButton,
  Paper,
  CircularProgress,
  useTheme,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import FileUploadIcon from '@mui/icons-material/FileUpload'
import CloseIcon from '@mui/icons-material/Close'
import InsertDriveFileIcon from '@mui/icons-material/InsertDriveFile'

function SearchHeader({
  searchTerm,
  onSearchChange,
  isSearching,
  file,
  onFileChange,
  uploading,
  verifying,
  progress,
  onUpload,
  onClearFile,
}) {
  const fileInputRef = useRef(null)
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const handleButtonClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  return (
    <Paper
      elevation={0}
      sx={{
        p: 2.5,
        mb: 3,
        borderRadius: '12px',
        backgroundColor: theme.palette.background.paper,
        border: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          gap: 2,
          alignItems: 'center',
        }}
      >
        {/* Semantic AI Search Field */}
        <TextField
          fullWidth
          size="small"
          placeholder="Search documents by keyword or semantic context..."
          value={searchTerm}
          onChange={(e) => onSearchChange(e.target.value)}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: theme.palette.text.secondary, fontSize: 20 }} />
                </InputAdornment>
              ),
              endAdornment: (
                <InputAdornment position="end">
                  {isSearching ? (
                    <CircularProgress size={18} sx={{ color: '#FF6B00' }} />
                  ) : (
                    searchTerm && (
                      <IconButton size="small" onClick={() => onSearchChange('')} edge="end">
                        <CloseIcon fontSize="small" sx={{ color: theme.palette.text.secondary }} />
                      </IconButton>
                    )
                  )}
                </InputAdornment>
              ),
            },
          }}
          sx={{
            flexGrow: 1,
            '& .MuiOutlinedInput-root': {
              borderRadius: '8px',
              backgroundColor: isDark ? '#141720' : '#F8FAFC',
              fontSize: '0.9rem',
              '& fieldset': { borderColor: theme.palette.divider },
              '&:hover fieldset': { borderColor: '#FF6B00' },
              '&.Mui-focused fieldset': { borderColor: '#FF6B00' },
            },
          }}
        />

        {/* Upload Action (Water Blue Button) */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexShrink: 0 }}>
          <input
            type="file"
            ref={fileInputRef}
            hidden
            onChange={onFileChange}
            accept=".txt,.md,.pdf,.docx"
            disabled={uploading}
          />

          <Button
            variant="contained"
            disabled={uploading}
            onClick={handleButtonClick}
            startIcon={<FileUploadIcon />}
            size="medium"
            sx={{
              backgroundColor: '#0284C7', // Water Blue
              color: '#FFFFFF',
              fontWeight: 700,
              fontSize: '0.85rem',
              textTransform: 'none',
              px: 2.5,
              py: 0.9,
              borderRadius: '8px',
              boxShadow: 'none',
              whiteSpace: 'nowrap',
              '&:hover': {
                backgroundColor: '#0369A1',
                boxShadow: 'none',
              },
              '&.Mui-disabled': {
                backgroundColor: isDark ? '#1E2430' : '#E2E8F0',
                color: theme.palette.text.secondary,
              },
            }}
          >
            {uploading ? (verifying ? 'Verifying...' : 'Uploading...') : 'Upload Document'}
          </Button>
        </Box>
      </Box>

      {/* Active File Stage Banner if file selected */}
      {file && (
        <Box
          sx={{
            mt: 2,
            p: 2,
            borderRadius: '8px',
            border: `1px solid ${theme.palette.divider}`,
            backgroundColor: isDark ? '#141720' : '#F8FAFC',
            display: 'flex',
            flexDirection: 'column',
            gap: 1.5,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, overflow: 'hidden' }}>
              <InsertDriveFileIcon sx={{ color: '#0284C7' }} />
              <Box sx={{ overflow: 'hidden' }}>
                <Typography
                  sx={{
                    fontSize: '0.88rem',
                    fontWeight: 700,
                    color: isDark ? '#F1F5F9' : '#0A0A0A',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {file.name}
                </Typography>
                <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
                  {(file.size / 1024).toFixed(1)} KB &bull; Ready to verify in S3
                </Typography>
              </Box>
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Button
                variant="contained"
                size="small"
                disabled={uploading}
                onClick={onUpload}
                sx={{
                  backgroundColor: '#16A34A',
                  color: '#FFFFFF',
                  fontWeight: 700,
                  fontSize: '0.8rem',
                  textTransform: 'none',
                  px: 2,
                  py: 0.65,
                  borderRadius: '6px',
                  boxShadow: 'none',
                  '&:hover': {
                    backgroundColor: '#15803D',
                    boxShadow: 'none',
                  },
                }}
              >
                {uploading ? (verifying ? 'Verifying S3...' : `Uploading ${progress}%`) : 'Confirm Upload'}
              </Button>
              <IconButton
                size="small"
                onClick={onClearFile}
                disabled={uploading}
                sx={{
                  border: `1px solid ${theme.palette.divider}`,
                  borderRadius: '6px',
                  p: 0.6,
                }}
              >
                <CloseIcon fontSize="small" sx={{ color: theme.palette.text.secondary }} />
              </IconButton>
            </Box>
          </Box>

          {/* Upload Progress Bar */}
          {uploading && (
            <Box sx={{ width: '100%', mt: 0.5 }}>
              <LinearProgress
                variant="determinate"
                value={progress}
                sx={{
                  height: 6,
                  borderRadius: 3,
                  backgroundColor: isDark ? '#1E2430' : '#E2E8F0',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: '#0284C7', // Water Blue
                  },
                }}
              />
            </Box>
          )}
        </Box>
      )}
    </Paper>
  )
}

export default React.memo(SearchHeader)
