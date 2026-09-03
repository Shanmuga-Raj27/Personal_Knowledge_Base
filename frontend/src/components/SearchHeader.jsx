import React, { useRef } from 'react'
import { Box, TextField, Button, InputAdornment, Typography, LinearProgress, IconButton, Paper, CircularProgress } from '@mui/material'
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
  onClearFile
}) {
  const fileInputRef = useRef(null)

  const handleButtonClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  return (
    <Paper 
      elevation={0}
      sx={{ 
        p: 3, 
        mb: 4, 
        borderRadius: '12px',
        backgroundColor: '#FFFFFF',
        border: '1px solid #E2E8F0',
      }}
    >
      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 2, alignItems: 'center' }}>
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
                  <SearchIcon sx={{ color: '#64748B', fontSize: 20 }} />
                </InputAdornment>
              ),
              endAdornment: (
                <InputAdornment position="end">
                  {isSearching ? (
                    <CircularProgress size={18} sx={{ color: '#64748B' }} />
                  ) : (
                    searchTerm && (
                      <IconButton size="small" onClick={() => onSearchChange('')} edge="end">
                        <CloseIcon fontSize="small" sx={{ color: '#64748B' }} />
                      </IconButton>
                    )
                  )}
                </InputAdornment>
              ),
            }
          }}
          sx={{
            flexGrow: 1,
            '& .MuiOutlinedInput-root': {
              borderRadius: '8px',
              backgroundColor: '#F8FAFC',
              fontSize: '0.9rem',
              '& fieldset': { borderColor: '#E2E8F0' },
              '&:hover fieldset': { borderColor: '#0A192F' },
              '&.Mui-focused fieldset': { borderColor: '#0A192F' },
            }
          }}
        />

        {/* Compact Upload Action */}
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
              backgroundColor: '#0A192F',
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
                backgroundColor: '#0F172A',
                boxShadow: 'none',
              },
              '&.Mui-disabled': {
                backgroundColor: '#E2E8F0',
                color: '#94A3B8'
              }
            }}
          >
            {uploading ? (verifying ? 'Verifying...' : 'Uploading...') : 'Upload File'}
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
            border: '1px solid #E2E8F0', 
            backgroundColor: '#F8FAFC',
            display: 'flex',
            flexDirection: 'column',
            gap: 1.5
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, overflow: 'hidden' }}>
              <InsertDriveFileIcon sx={{ color: '#0A192F' }} />
              <Box sx={{ overflow: 'hidden' }}>
                <Typography sx={{ fontSize: '0.85rem', fontWeight: 700, color: '#0F172A', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {file.name}
                </Typography>
                <Typography variant="caption" sx={{ color: '#64748B' }}>
                  {(file.size / 1024).toFixed(1)} KB
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
                  fontSize: '0.78rem',
                  textTransform: 'none',
                  px: 2,
                  py: 0.6,
                  borderRadius: '6px',
                  boxShadow: 'none',
                  '&:hover': {
                    backgroundColor: '#15803D',
                    boxShadow: 'none',
                  }
                }}
              >
                {uploading ? (verifying ? 'Verifying S3...' : `Uploading ${progress}%`) : 'Confirm Upload'}
              </Button>
              <IconButton 
                size="small" 
                onClick={onClearFile} 
                disabled={uploading} 
                sx={{ border: '1px solid #E2E8F0', borderRadius: '6px' }}
              >
                <CloseIcon fontSize="small" sx={{ color: '#64748B' }} />
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
                  backgroundColor: '#E2E8F0',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: '#16A34A'
                  }
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
