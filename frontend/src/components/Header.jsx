import React from 'react'
import { AppBar, Toolbar, Typography, Box, Container } from '@mui/material'

export default function Header({ backendStatus }) {
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
        </Toolbar>
      </Container>
    </AppBar>
  )
}
