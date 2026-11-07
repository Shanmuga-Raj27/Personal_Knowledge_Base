import React, { useState } from 'react'
import {
  AppBar,
  Toolbar,
  Typography,
  Box,
  Container,
  Avatar,
  Menu,
  MenuItem,
  Divider,
  ListItemIcon,
  IconButton,
  Tooltip,
  useTheme,
} from '@mui/material'
import Logout from '@mui/icons-material/Logout'
import MenuIcon from '@mui/icons-material/Menu'
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined'
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined'
import { SwanLogo } from '../pages/LandingPage'

function Header({
  backendStatus,
  currentUser,
  onLogout,
  onToggleSidebar,
  sidebarOpen,
  themeMode,
  onToggleTheme,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const [anchorEl, setAnchorEl] = useState(null)
  const open = Boolean(anchorEl)

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget)
  }

  const handleMenuClose = () => {
    setAnchorEl(null)
  }

  const handleLogoutClick = () => {
    handleMenuClose()
    if (onLogout) {
      onLogout()
    }
  }

  const userInitial = currentUser?.email
    ? currentUser.email.charAt(0).toUpperCase()
    : 'U'

  return (
    <AppBar
      position="sticky"
      elevation={0}
      sx={{
        backgroundColor: isDark ? '#0A0C10' : '#FFFFFF',
        borderBottom: `1px solid ${theme.palette.divider}`,
        color: isDark ? '#F1F5F9' : '#0A0A0A',
        zIndex: 1200,
      }}
    >
      <Container maxWidth={false} sx={{ px: { xs: 2, sm: 3 } }}>
        <Toolbar
          disableGutters
          sx={{
            height: 64,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          {/* Left: Sidebar Toggle, Logo & Status Indicator */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 1, sm: 2 } }}>
            {currentUser && onToggleSidebar && (
              <Tooltip title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}>
                <IconButton
                  onClick={onToggleSidebar}
                  size="small"
                  edge="start"
                  aria-label="Toggle navigation menu"
                  sx={{
                    color: isDark ? '#F1F5F9' : '#0A0A0A',
                    p: 0.85,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '8px',
                    '&:hover': {
                      backgroundColor: isDark ? 'rgba(255, 255, 255, 0.05)' : '#F8FAFC',
                      borderColor: '#FF6B00',
                    },
                  }}
                >
                  <MenuIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}

            {/* Brand Logo & Name */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2 }}>
              <SwanLogo size={28} />
              <Typography
                variant="h6"
                sx={{
                  fontFamily: "Georgia, 'Times New Roman', Cambria, serif",
                  fontWeight: 700,
                  fontSize: '1.25rem',
                  letterSpacing: '-0.02em',
                  color: isDark ? '#FFFFFF' : '#0A0A0A',
                  cursor: 'default',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.5,
                }}
              >
                Swan <Box component="span" sx={{ color: '#FF6B00' }}>Drive</Box>
              </Typography>
            </Box>

            {/* Connection Status Pill */}
            <Box
              sx={{
                display: { xs: 'none', sm: 'flex' },
                alignItems: 'center',
                gap: 0.8,
                px: 1.2,
                py: 0.35,
                borderRadius: '16px',
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: isDark ? '#141720' : '#F8FAFC',
              }}
            >
              <Box
                sx={{
                  width: 7,
                  height: 7,
                  borderRadius: '50%',
                  backgroundColor:
                    backendStatus === 'online'
                      ? '#16A34A'
                      : backendStatus === 'offline'
                      ? '#DC2626'
                      : '#EAB308',
                  animation: backendStatus === 'checking' ? 'pulse 1.5s infinite' : 'none',
                  '@keyframes pulse': {
                    '0%': { transform: 'scale(0.8)', opacity: 0.5 },
                    '50%': { transform: 'scale(1.2)', opacity: 1 },
                    '100%': { transform: 'scale(0.8)', opacity: 0.5 },
                  },
                }}
              />
              <Typography
                sx={{
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  color: theme.palette.text.secondary,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                {backendStatus === 'online' ? 'Online' : backendStatus === 'offline' ? 'Offline' : 'Connecting'}
              </Typography>
            </Box>
          </Box>

          {/* Right: Theme Toggle & User Session Dropdown */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            {/* Theme Toggle Button */}
            {onToggleTheme && (
              <Tooltip title={isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme'}>
                <IconButton
                  onClick={onToggleTheme}
                  size="small"
                  aria-label="Toggle theme mode"
                  sx={{
                    color: theme.palette.text.secondary,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '8px',
                    p: 0.85,
                    '&:hover': {
                      backgroundColor: isDark ? 'rgba(255, 255, 255, 0.05)' : '#F8FAFC',
                      color: isDark ? '#FFFFFF' : '#0A0A0A',
                    },
                  }}
                >
                  {isDark ? <LightModeOutlinedIcon fontSize="small" /> : <DarkModeOutlinedIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
            )}

            {/* User Session Avatar Dropdown */}
            {currentUser && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography
                  variant="body2"
                  sx={{
                    color: theme.palette.text.secondary,
                    fontWeight: 600,
                    fontSize: '0.85rem',
                    display: { xs: 'none', md: 'block' },
                  }}
                >
                  {currentUser.email || `User #${currentUser.id ?? ''}`}
                </Typography>
                <Avatar
                  onClick={handleMenuOpen}
                  sx={{
                    bgcolor: '#FF6B00', // Swan Drive Orange
                    color: '#FFFFFF',
                    width: 36,
                    height: 36,
                    fontSize: '0.95rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    border: `2px solid ${isDark ? '#262D3D' : '#FFFFFF'}`,
                    boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1)',
                    transition: 'transform 0.15s, opacity 0.15s',
                    '&:hover': {
                      transform: 'scale(1.04)',
                      opacity: 0.9,
                    },
                  }}
                >
                  {userInitial}
                </Avatar>

                <Menu
                  anchorEl={anchorEl}
                  id="account-menu"
                  open={open}
                  onClose={handleMenuClose}
                  transformOrigin={{ horizontal: 'right', vertical: 'top' }}
                  anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
                  slotProps={{
                    paper: {
                      elevation: 0,
                      sx: {
                        overflow: 'visible',
                        filter: isDark
                          ? 'drop-shadow(0px 4px 16px rgba(0,0,0,0.6))'
                          : 'drop-shadow(0px 4px 16px rgba(0,0,0,0.08))',
                        mt: 1.5,
                        border: `1px solid ${theme.palette.divider}`,
                        borderRadius: '10px',
                        width: 220,
                        backgroundColor: theme.palette.background.paper,
                      },
                    },
                  }}
                >
                  <Box sx={{ px: 2, py: 1.5 }}>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 700,
                        color: isDark ? '#FFFFFF' : '#0A0A0A',
                      }}
                    >
                      Swan Drive Session
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{ color: theme.palette.text.secondary, wordBreak: 'break-all' }}
                    >
                      {currentUser.email || `User #${currentUser.id ?? ''}`}
                    </Typography>
                  </Box>
                  <Divider sx={{ borderColor: theme.palette.divider }} />
                  <MenuItem
                    onClick={handleLogoutClick}
                    sx={{
                      py: 1.2,
                      '&:hover': {
                        backgroundColor: isDark ? 'rgba(255, 255, 255, 0.05)' : '#F8FAFC',
                      },
                    }}
                  >
                    <ListItemIcon>
                      <Logout fontSize="small" sx={{ color: theme.palette.text.secondary }} />
                    </ListItemIcon>
                    <Typography
                      variant="body2"
                      sx={{ fontWeight: 600, color: isDark ? '#F1F5F9' : '#0A0A0A' }}
                    >
                      Sign Out
                    </Typography>
                  </MenuItem>
                </Menu>
              </Box>
            )}
          </Box>
        </Toolbar>
      </Container>
    </AppBar>
  )
}

export default React.memo(Header)
