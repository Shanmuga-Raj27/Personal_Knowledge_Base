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
  Chip
} from '@mui/material'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import FolderOutlinedIcon from '@mui/icons-material/FolderOutlined'
import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined'
import { useKnowledgeBaseFiles } from '../context/KnowledgeBaseFilesContext'

const DRAWER_WIDTH_OPEN = 240
const DRAWER_WIDTH_COLLAPSED = 72

function Sidebar({ open, onToggle, currentView, onViewChange }) {
  const { selected } = useKnowledgeBaseFiles()

  const navItems = [
    {
      id: 'vault',
      label: 'Vault',
      icon: <FolderOutlinedIcon fontSize="small" />,
      badge: null
    },
    {
      id: 'knowledge',
      label: 'Knowledge Base',
      icon: <AutoAwesomeOutlinedIcon fontSize="small" />,
      badge: selected.length > 0 ? selected.length : null
    }
  ]

  const currentWidth = open ? DRAWER_WIDTH_OPEN : DRAWER_WIDTH_COLLAPSED

  return (
    <Box
      component="nav"
      aria-label="Navigation Sidebar"
      sx={{
        width: currentWidth,
        flexShrink: 0,
        transition: (theme) =>
          theme.transitions.create('width', {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.enteringScreen
          })
      }}
    >
      <Box
        sx={{
          width: currentWidth,
          height: '100%',
          minHeight: 'calc(100vh - 64px)',
          backgroundColor: '#FFFFFF',
          borderRight: '1px solid #E2E8F0',
          display: 'flex',
          flexDirection: 'column',
          transition: (theme) =>
            theme.transitions.create('width', {
              easing: theme.transitions.easing.sharp,
              duration: theme.transitions.duration.enteringScreen
            }),
          overflowX: 'hidden'
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
            minHeight: 56
          }}
        >
          {open && (
            <Typography
              variant="caption"
              sx={{
                fontWeight: 700,
                color: '#64748B',
                textTransform: 'uppercase',
                letterSpacing: '0.06em'
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
                color: '#64748B',
                border: '1px solid #E2E8F0',
                borderRadius: '8px',
                p: 0.75,
                '&:hover': {
                  backgroundColor: '#F8FAFC',
                  color: '#0A192F',
                  borderColor: '#CBD5E1'
                }
              }}
            >
              {open ? <ChevronLeftIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
        </Box>

        <Divider sx={{ borderColor: '#E2E8F0' }} />

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
                  backgroundColor: isSelected ? '#0A192F' : 'transparent',
                  color: isSelected ? '#FFFFFF' : '#475569',
                  transition: 'all 0.15s ease-in-out',
                  '&:hover': {
                    backgroundColor: isSelected ? '#0F172A' : '#F1F5F9',
                    color: isSelected ? '#FFFFFF' : '#0A192F'
                  },
                  '&.Mui-selected': {
                    backgroundColor: '#0A192F',
                    color: '#FFFFFF',
                    '&:hover': {
                      backgroundColor: '#0F172A'
                    }
                  }
                }}
              >
                <ListItemIcon
                  sx={{
                    minWidth: 0,
                    mr: open ? 2 : 'auto',
                    justifyContent: 'center',
                    color: isSelected ? '#FFFFFF' : '#64748B'
                  }}
                >
                  {item.icon}
                </ListItemIcon>

                {open && (
                  <ListItemText
                    primary={
                      <Typography
                        sx={{
                          fontSize: '0.9rem',
                          fontWeight: isSelected ? 700 : 500,
                          color: isSelected ? '#FFFFFF' : '#334155'
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
                      backgroundColor: isSelected ? 'rgba(255, 255, 255, 0.2)' : '#EFF6FF',
                      color: isSelected ? '#FFFFFF' : '#1D4ED8',
                      borderRadius: '6px'
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
      </Box>
    </Box>
  )
}

export default React.memo(Sidebar)
