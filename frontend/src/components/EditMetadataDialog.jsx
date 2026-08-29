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
  Chip
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
  onSave
}) {
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
            borderRadius: '12px',
            border: '1px solid #E2E8F0',
            backgroundColor: '#FFFFFF',
            p: 1
          }
        }
      }}
    >
      <DialogTitle sx={{ fontWeight: 800, fontSize: '1.2rem', color: '#0F172A', pt: 2, pb: 1 }}>
        Edit Document Metadata
      </DialogTitle>
      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, py: 2 }}>
        {/* Original File Indicator */}
        <Box sx={{ p: 1.5, borderRadius: '8px', border: '1px solid #E2E8F0', backgroundColor: '#F8FAFC' }}>
          <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 700, textTransform: 'uppercase', display: 'block', mb: 0.5 }}>
            Original File
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 600, color: '#0F172A' }}>
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
          InputLabelProps={{ shrink: true }}
          inputProps={{ maxLength: 100 }}
          helperText={
            <Box component="span" sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', m: 0 }}>
              <span />
              <Typography component="span" variant="caption" sx={{ color: getCounterColor(editTitle.length, 100), fontWeight: 600 }}>
                {editTitle.length}/100
              </Typography>
            </Box>
          }
          sx={{
            '& .MuiOutlinedInput-root': {
              borderRadius: '8px',
              '& fieldset': { borderColor: '#E2E8F0' },
              '&:hover fieldset': { borderColor: '#0A192F' },
              '&.Mui-focused fieldset': { borderColor: '#0A192F' },
            }
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
          InputLabelProps={{ shrink: true }}
          inputProps={{ maxLength: 255 }}
          helperText={
            <Box component="span" sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', m: 0 }}>
              <span />
              <Typography component="span" variant="caption" sx={{ color: getCounterColor(editDescription.length, 255), fontWeight: 600 }}>
                {editDescription.length}/255
              </Typography>
            </Box>
          }
          sx={{
            '& .MuiOutlinedInput-root': {
              borderRadius: '8px',
              '& fieldset': { borderColor: '#E2E8F0' },
              '&:hover fieldset': { borderColor: '#0A192F' },
              '&.Mui-focused fieldset': { borderColor: '#0A192F' },
            }
          }}
        />

        {/* Tag Manager */}
        <Box>
          <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 700, textTransform: 'uppercase', display: 'block', mb: 1 }}>
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
              inputProps={{ maxLength: 50 }}
              error={tagInputExceeds || (combinedExceeds && !!tagInput.trim())}
              helperText={
                tagInputExceeds ? (
                  <Typography component="span" variant="caption" sx={{ color: 'error.main', fontWeight: 600 }}>
                    Tag exceeds maximum 50 characters.
                  </Typography>
                ) : (combinedExceeds && !!tagInput.trim()) ? (
                  <Typography component="span" variant="caption" sx={{ color: 'error.main', fontWeight: 600 }}>
                    Adding this tag exceeds combined limit of 50 characters ({projectedCombinedLength}/50).
                  </Typography>
                ) : (
                  <Box component="span" sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', m: 0 }}>
                    <Typography component="span" variant="caption" sx={{ color: getCounterColor(currentCombinedLength, 50), fontWeight: 600 }}>
                      Combined Tags: {currentCombinedLength}/50
                    </Typography>
                    <Typography component="span" variant="caption" sx={{ color: getCounterColor(tagInput.length, 50), fontWeight: 600 }}>
                      {tagInput.length}/50
                    </Typography>
                  </Box>
                )
              }
              sx={{
                flexGrow: 1,
                '& .MuiOutlinedInput-root': {
                  borderRadius: '8px',
                  '& fieldset': { borderColor: '#E2E8F0' },
                  '&:hover fieldset': { borderColor: '#0A192F' },
                  '&.Mui-focused fieldset': { borderColor: '#0A192F' },
                }
              }}
            />
            <Button
              variant="outlined"
              onClick={onAddTag}
              disabled={isAddDisabled}
              sx={{
                borderColor: '#CBD5E1',
                color: '#0F172A',
                fontWeight: 700,
                borderRadius: '8px',
                '&:hover': { borderColor: '#0A192F', backgroundColor: '#F8FAFC' }
              }}
            >
              Add
            </Button>
          </Box>

          {/* Tags List */}
          <Box sx={{ display: 'flex', gap: 0.8, flexWrap: 'wrap', minHeight: 32 }}>
            {editTags.length === 0 ? (
              <Typography variant="caption" sx={{ color: '#94A3B8', fontStyle: 'italic', alignSelf: 'center' }}>
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
                    borderColor: '#CBD5E1',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    backgroundColor: '#F8FAFC'
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
          sx={{ color: '#64748B', fontWeight: 600, '&:hover': { color: '#0F172A' } }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={onSave}
          sx={{
            backgroundColor: '#0A192F',
            color: '#FFFFFF',
            fontWeight: 700,
            borderRadius: '8px',
            boxShadow: 'none',
            '&:hover': { backgroundColor: '#0F172A', boxShadow: 'none' }
          }}
        >
          Save Changes
        </Button>
      </DialogActions>
    </Dialog>
  )
}
