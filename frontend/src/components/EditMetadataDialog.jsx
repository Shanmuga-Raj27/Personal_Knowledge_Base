import React from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Box,
  Typography,
  Chip,
  useTheme,
} from '@mui/material'
import TagIcon from '@mui/icons-material/LocalOffer'

const getCounterColor = (current, max) => {
  const ratio = current / max
  if (ratio >= 1.0) return 'error.main'
  if (ratio >= 0.8) return 'warning.main'
  return 'text.secondary'
}

export default function EditMetadataDialog({
  open,
  onClose,
  editingDoc,
  editTitle,
  setEditTitle,
  editDescription,
  setEditDescription,
  editTags,
  tagInput,
  setTagInput,
  onAddTag,
  onRemoveTag,
  onSave,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const currentCombinedLength = editTags.join(',').length
  const newTagLength = tagInput.trim().length
  const projectedCombinedLength = editTags.length > 0 ? currentCombinedLength + 1 + newTagLength : newTagLength
  const tagInputExceeds = tagInput.length > 50
  const combinedExceeds = projectedCombinedLength > 50
  const isAddDisabled = !tagInput.trim() || tagInputExceeds || combinedExceeds || editTags.includes(tagInput.trim())

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
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
          fontSize: '1.25rem',
          color: isDark ? '#FFFFFF' : '#0A0A0A',
          pt: 2,
          pb: 1,
        }}
      >
        Edit Document Metadata
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, py: 2 }}>
        {/* Original File Indicator */}
        <Box
          sx={{
            p: 1.5,
            borderRadius: '8px',
            border: `1px solid ${theme.palette.divider}`,
            backgroundColor: isDark ? '#141720' : '#F8FAFC',
          }}
        >
          <Typography
            variant="caption"
            sx={{
              color: theme.palette.text.secondary,
              fontWeight: 700,
              textTransform: 'uppercase',
              display: 'block',
              mb: 0.3,
            }}
          >
            Original File
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 600, color: isDark ? '#F1F5F9' : '#0A0A0A' }}>
            {editingDoc?.filename}
          </Typography>
        </Box>

        {/* Title Input */}
        <TextField
          label="Document Title"
          fullWidth
          size="small"
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value.slice(0, 100))}
          placeholder="e.g. Q3 Financial Statement"
          slotProps={{
            inputLabel: { shrink: true },
            htmlInput: { maxLength: 100 },
          }}
          helperText={
            <Box component="span" sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', m: 0 }}>
              <span />
              <Typography
                component="span"
                variant="caption"
                sx={{ color: getCounterColor(editTitle.length, 100), fontWeight: 600 }}
              >
                {editTitle.length}/100
              </Typography>
            </Box>
          }
          sx={{
            '& .MuiOutlinedInput-root': {
              borderRadius: '8px',
              backgroundColor: isDark ? '#141720' : '#FBFBFC',
              '& fieldset': { borderColor: theme.palette.divider },
              '&:hover fieldset': { borderColor: '#FF6B00' },
              '&.Mui-focused fieldset': { borderColor: '#FF6B00' },
            },
          }}
        />

        {/* Description Input */}
        <TextField
          label="Description"
          fullWidth
          multiline
          rows={3}
          value={editDescription}
          onChange={(e) => setEditDescription(e.target.value.slice(0, 255))}
          placeholder="Brief summary of document content..."
          slotProps={{
            inputLabel: { shrink: true },
            htmlInput: { maxLength: 255 },
          }}
          helperText={
            <Box component="span" sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', m: 0 }}>
              <span />
              <Typography
                component="span"
                variant="caption"
                sx={{ color: getCounterColor(editDescription.length, 255), fontWeight: 600 }}
              >
                {editDescription.length}/255
              </Typography>
            </Box>
          }
          sx={{
            '& .MuiOutlinedInput-root': {
              borderRadius: '8px',
              backgroundColor: isDark ? '#141720' : '#FBFBFC',
              '& fieldset': { borderColor: theme.palette.divider },
              '&:hover fieldset': { borderColor: '#FF6B00' },
              '&.Mui-focused fieldset': { borderColor: '#FF6B00' },
            },
          }}
        />

        {/* Tag Manager */}
        <Box>
          <Typography
            variant="caption"
            sx={{
              color: theme.palette.text.secondary,
              fontWeight: 700,
              textTransform: 'uppercase',
              display: 'block',
              mb: 1,
            }}
          >
            Tags
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, mb: 1.5 }}>
            <TextField
              size="small"
              placeholder="Add tag and press Enter"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value.slice(0, 50))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  if (!isAddDisabled) {
                    onAddTag()
                  }
                }
              }}
              slotProps={{
                htmlInput: { maxLength: 50 },
              }}
              error={tagInputExceeds || (combinedExceeds && !!tagInput.trim())}
              helperText={
                tagInputExceeds ? (
                  <Typography component="span" variant="caption" sx={{ color: 'error.main', fontWeight: 600 }}>
                    Tag exceeds maximum 50 characters.
                  </Typography>
                ) : combinedExceeds && !!tagInput.trim() ? (
                  <Typography component="span" variant="caption" sx={{ color: 'error.main', fontWeight: 600 }}>
                    Adding this tag exceeds combined limit of 50 characters ({projectedCombinedLength}/50).
                  </Typography>
                ) : (
                  <Box component="span" sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', m: 0 }}>
                    <Typography
                      component="span"
                      variant="caption"
                      sx={{ color: getCounterColor(currentCombinedLength, 50), fontWeight: 600 }}
                    >
                      Combined Tags: {currentCombinedLength}/50
                    </Typography>
                    <Typography
                      component="span"
                      variant="caption"
                      sx={{ color: getCounterColor(tagInput.length, 50), fontWeight: 600 }}
                    >
                      {tagInput.length}/50
                    </Typography>
                  </Box>
                )
              }
              sx={{
                flexGrow: 1,
                '& .MuiOutlinedInput-root': {
                  borderRadius: '8px',
                  backgroundColor: isDark ? '#141720' : '#FBFBFC',
                  '& fieldset': { borderColor: theme.palette.divider },
                  '&:hover fieldset': { borderColor: '#FF6B00' },
                  '&.Mui-focused fieldset': { borderColor: '#FF6B00' },
                },
              }}
            />
            <Button
              variant="outlined"
              onClick={onAddTag}
              disabled={isAddDisabled}
              sx={{
                borderColor: theme.palette.divider,
                color: isDark ? '#FFFFFF' : '#0A0A0A',
                fontWeight: 600,
                borderRadius: '8px',
                '&:hover': {
                  borderColor: '#FF6B00',
                  backgroundColor: isDark ? 'rgba(255, 107, 0, 0.08)' : '#FFF5EE',
                },
              }}
            >
              Add
            </Button>
          </Box>

          {/* Tags List */}
          <Box sx={{ display: 'flex', gap: 0.8, flexWrap: 'wrap', minHeight: 32 }}>
            {editTags.length === 0 ? (
              <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontStyle: 'italic', alignSelf: 'center' }}>
                No tags added yet.
              </Typography>
            ) : (
              editTags.map((tag) => (
                <Chip
                  key={tag}
                  label={tag}
                  icon={<TagIcon style={{ fontSize: 14 }} />}
                  onDelete={() => onRemoveTag(tag)}
                  variant="outlined"
                  sx={{
                    borderRadius: '6px',
                    borderColor: theme.palette.divider,
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    backgroundColor: isDark ? '#141720' : '#F8FAFC',
                    color: isDark ? '#F1F5F9' : '#334155',
                  }}
                />
              ))
            )}
          </Box>
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
        <Button
          onClick={onClose}
          sx={{ color: theme.palette.text.secondary, fontWeight: 600, '&:hover': { color: '#0A0A0A' } }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={onSave}
          sx={{
            backgroundColor: '#0284C7', // Water Blue
            color: '#FFFFFF',
            fontWeight: 700,
            borderRadius: '8px',
            boxShadow: 'none',
            px: 2.5,
            '&:hover': { backgroundColor: '#0369A1', boxShadow: 'none' },
          }}
        >
          Save Changes
        </Button>
      </DialogActions>
    </Dialog>
  )
}
