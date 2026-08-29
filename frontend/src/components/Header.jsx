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
  ListItemIcon
} from '@mui/material'
import Logout from '@mui/icons-material/Logout'
import AccountCircle from '@mui/icons-material/AccountCircle'

export default function Header({ backendStatus, currentUser, onLogout }) {
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
      position="static"
      elevation={0}
      sx={{
        backgroundColor: '#FFFFFF',
        borderBottom: '1px solid #E2E8F0',
        color: '#0F172A'
      }}
    >
      <Container maxWidth="lg">
        <Toolbar disableGutters sx={{ height: 64, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {/* Logo & Status Indicator */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography
              variant="h6"
              sx={{
                fontWeight: 800,
                fontSize: '1.25rem',
                letterSpacing: '-0.02em',
                color: '#0A192F',
                cursor: 'default'
              }}
            >
              Personal Knowledge Base
            </Typography>

            {/* Connection Dot Indicator */}
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 1.5,
                py: 0.4,
                borderRadius: '16px',
                border: '1px solid #E2E8F0',
                backgroundColor: '#F8FAFC'
              }}
            >
              <Box
                sx={{
                  width: 7,
                  height: 7,
                  borderRadius: '50%',
                  backgroundColor: backendStatus === 'online' ? '#16A34A' : backendStatus === 'offline' ? '#DC2626' : '#EAB308',
                  animation: backendStatus === 'checking' ? 'pulse 1.5s infinite' : 'none',
                  '@keyframes pulse': {
                    '0%': { transform: 'scale(0.8)', opacity: 0.5 },
                    '50%': { transform: 'scale(1.2)', opacity: 1 },
                    '100%': { transform: 'scale(0.8)', opacity: 0.5 },
                  }
                }}
              />
              <Typography
                sx={{
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  color: '#64748B',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em'
                }}
              >
                {backendStatus === 'online' ? 'Online' : backendStatus === 'offline' ? 'Offline' : 'Connecting'}
              </Typography>
            </Box>
          </Box>

          {/* User Session Avatar Dropdown */}
          {currentUser && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography
                variant="body2"
                sx={{
                  color: '#64748B',
                  fontWeight: 600,
                  display: { xs: 'none', sm: 'block' }
                }}
              >
                {currentUser.email}
              </Typography>
              <Avatar
                onClick={handleMenuOpen}
                sx={{
                  bgcolor: '#0A192F',
                  width: 36,
                  height: 36,
                  fontSize: '0.95rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  border: '2px solid #E2E8F0',
                  boxShadow: '0 1px 3px 0 rgb(0 0 0 / 0.1)',
                  transition: 'opacity 0.2s',
                  '&:hover': {
                    opacity: 0.85
                  }
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
                      filter: 'drop-shadow(0px 2px 8px rgba(0,0,0,0.32))',
                      mt: 1.5,
                      border: '1px solid #E2E8F0',
                      borderRadius: '8px',
                      width: 200,
                      '& .MuiAvatar-root': {
                        width: 32,
                        height: 32,
                        ml: -0.5,
                        mr: 1,
                      },
                    },
                  }
                }}
              >
                <Box sx={{ px: 2, py: 1.5 }}>
                  <Typography variant="body2" sx={{ fontWeight: 800, color: '#0F172A' }}>
                    User Session
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#64748B', wordBreak: 'break-all' }}>
                    {currentUser.email}
                  </Typography>
                </Box>
                <Divider />
                <MenuItem onClick={handleLogoutClick} sx={{ py: 1 }}>
                  <ListItemIcon>
                    <Logout fontSize="small" sx={{ color: '#64748B' }} />
                  </ListItemIcon>
                  <Typography variant="body2" sx={{ fontWeight: 600, color: '#0F172A' }}>
                    Sign Out
                  </Typography>
                </MenuItem>
              </Menu>
            </Box>
          )}
        </Toolbar>
      </Container>
    </AppBar>
  )
}
