import React from 'react'
import {
  Box,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  IconButton,
  Typography,
  Tooltip,
  Divider,
  Chip,
  useTheme,
} from '@mui/material'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import FolderOutlinedIcon from '@mui/icons-material/FolderOutlined'
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined'
import { useKnowledgeBaseFiles } from '../context/KnowledgeBaseFilesContext'

const DRAWER_WIDTH_OPEN = 240
const DRAWER_WIDTH_COLLAPSED = 72

function Sidebar({ open, onToggle, currentView, onViewChange }) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const { selected } = useKnowledgeBaseFiles()

  const navItems = [
    {
      id: 'vault',
      label: 'My Drive',
      icon: <FolderOutlinedIcon fontSize="small" />,
      badge: null,
    },
    {
      id: 'knowledge',
      label: 'Swan AI',
      icon: <AutoAwesomeOutlinedIcon fontSize="small" />,
      badge: selected.length > 0 ? selected.length : null,
    },
  ]

  const currentWidth = open ? DRAWER_WIDTH_OPEN : DRAWER_WIDTH_COLLAPSED

  return (
    <Box
      component="nav"
      aria-label="Navigation Sidebar"
      sx={{
        width: currentWidth,
        flexShrink: 0,
        transition: theme.transitions.create('width', {
          easing: theme.transitions.easing.sharp,
          duration: theme.transitions.duration.enteringScreen,
        }),
      }}
    >
      <Box
        sx={{
          width: currentWidth,
          height: '100%',
          minHeight: 'calc(100vh - 64px)',
          backgroundColor: isDark ? '#0A0C10' : '#FFFFFF',
          borderRight: `1px solid ${theme.palette.divider}`,
          display: 'flex',
          flexDirection: 'column',
          transition: theme.transitions.create('width', {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.enteringScreen,
          }),
          overflowX: 'hidden',
        }}
      >
        {/* Sidebar Header & Collapse Toggle */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: open ? 'space-between' : 'center',
            px: open ? 2.5 : 1,
            py: 2,
            minHeight: 56,
          }}
        >
          {open && (
            <Typography
              variant="caption"
              sx={{
                fontWeight: 700,
                color: theme.palette.text.secondary,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                fontSize: '0.72rem',
              }}
            >
              Workspace
            </Typography>
          )}
          <Tooltip title={open ? 'Collapse sidebar' : 'Expand sidebar'} placement="right">
            <IconButton
              size="small"
              onClick={onToggle}
              aria-label={open ? 'Collapse sidebar' : 'Expand sidebar'}
              sx={{
                color: theme.palette.text.secondary,
                border: `1px solid ${theme.palette.divider}`,
                borderRadius: '8px',
                p: 0.75,
                '&:hover': {
                  backgroundColor: isDark ? 'rgba(255, 255, 255, 0.05)' : '#F8FAFC',
                  color: isDark ? '#FFFFFF' : '#0A0A0A',
                  borderColor: '#FF6B00',
                },
              }}
            >
              {open ? <ChevronLeftIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
        </Box>

        <Divider sx={{ borderColor: theme.palette.divider }} />

        {/* Navigation Items */}
        <List sx={{ px: 1.5, py: 2, flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 0.75 }}>
          {navItems.map((item) => {
            const isSelected = currentView === item.id

            const buttonContent = (
              <ListItemButton
                selected={isSelected}
                onClick={() => onViewChange(item.id)}
                sx={{
                  minHeight: 46,
                  borderRadius: '10px',
                  px: open ? 2 : 1.75,
                  justifyContent: open ? 'initial' : 'center',
                  backgroundColor: isSelected
                    ? (isDark ? 'rgba(255, 107, 0, 0.15)' : '#FFF5EE')
                    : 'transparent',
                  color: isSelected ? '#FF6B00' : theme.palette.text.secondary,
                  border: isSelected
                    ? `1px solid ${isDark ? 'rgba(255, 107, 0, 0.35)' : '#FFD8BF'}`
                    : '1px solid transparent',
                  transition: 'all 0.15s ease-in-out',
                  '&:hover': {
                    backgroundColor: isSelected
                      ? (isDark ? 'rgba(255, 107, 0, 0.2)' : '#FFF0E5')
                      : (isDark ? 'rgba(255, 255, 255, 0.04)' : '#F1F5F9'),
                    color: isSelected ? '#FF6B00' : (isDark ? '#F1F5F9' : '#0A0A0A'),
                  },
                  '&.Mui-selected': {
                    backgroundColor: isDark ? 'rgba(255, 107, 0, 0.15)' : '#FFF5EE',
                    color: '#FF6B00',
                    '&:hover': {
                      backgroundColor: isDark ? 'rgba(255, 107, 0, 0.2)' : '#FFF0E5',
                    },
                  },
                }}
              >
                <ListItemIcon
                  sx={{
                    minWidth: 0,
                    mr: open ? 2 : 'auto',
                    justifyContent: 'center',
                    color: isSelected ? '#FF6B00' : theme.palette.text.secondary,
                  }}
                >
                  {item.icon}
                </ListItemIcon>

                {open && (
                  <ListItemText
                    primary={
                      <Typography
                        sx={{
                          fontSize: '0.88rem',
                          fontWeight: isSelected ? 700 : 500,
                          color: isSelected ? '#FF6B00' : (isDark ? '#E2E8F0' : '#334155'),
                        }}
                      >
                        {item.label}
                      </Typography>
                    }
                    sx={{ opacity: open ? 1 : 0 }}
                  />
                )}

                {open && item.badge !== null && (
                  <Chip
                    label={item.badge}
                    size="small"
                    sx={{
                      height: 20,
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      backgroundColor: '#0284C7', // Water Blue
                      color: '#FFFFFF',
                      borderRadius: '6px',
                    }}
                  />
                )}
              </ListItemButton>
            )

            return (
              <ListItem key={item.id} disablePadding sx={{ display: 'block' }}>
                {!open ? (
                  <Tooltip title={item.label} placement="right" arrow>
                    {buttonContent}
                  </Tooltip>
                ) : (
                  buttonContent
                )}
              </ListItem>
            )
          })}
        </List>

        {/* Footer info in sidebar when open */}
        {open && (
          <Box sx={{ p: 2, borderTop: `1px solid ${theme.palette.divider}` }}>
            <Box
              sx={{
                p: 1.5,
                borderRadius: '8px',
                backgroundColor: isDark ? '#12151D' : '#F8FAFC',
                border: `1px solid ${theme.palette.divider}`,
              }}
            >
              <Typography variant="caption" sx={{ fontWeight: 700, color: theme.palette.text.secondary, display: 'block' }}>
                Swan Drive
              </Typography>
              <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontSize: '0.72rem' }}>
                Secure Storage &bull; Smart AI
              </Typography>
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  )
}

export default React.memo(Sidebar)
