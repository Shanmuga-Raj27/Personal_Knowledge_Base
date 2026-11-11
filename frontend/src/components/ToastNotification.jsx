import React from 'react'
import {
  Snackbar,
  Box,
  Typography,
  IconButton,
  Slide,
  CircularProgress,
  useTheme,
} from '@mui/material'
import CheckCircleOutlinedIcon from '@mui/icons-material/CheckCircleOutlined'
import ErrorOutlineOutlinedIcon from '@mui/icons-material/ErrorOutlineOutlined'
import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import CloseIcon from '@mui/icons-material/Close'

function SlideTransition(props) {
  return <Slide {...props} direction="down" />
}

/**
 * ToastNotification
 *
 * Compact translucent glass-style notification system.
 * Supports 'success', 'error', 'warning', 'info', and 'processing' states.
 * Automatically dismisses after 5 seconds with smooth entrance/exit animations.
 */
export default function ToastNotification({
  open,
  onClose,
  message,
  severity = 'info', // 'success' | 'error' | 'warning' | 'info' | 'processing'
  action,
  autoHideDuration = 5000,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  if (!open || !message) return null

  // Severity styling configurations
  const severityConfigs = {
    success: {
      icon: (
        <CheckCircleOutlinedIcon
          sx={{ fontSize: 18, color: isDark ? '#4ADE80' : '#16A34A', flexShrink: 0 }}
        />
      ),
      bg: isDark ? 'rgba(20, 36, 27, 0.85)' : 'rgba(240, 253, 244, 0.92)',
      border: isDark ? 'rgba(74, 222, 128, 0.35)' : 'rgba(134, 239, 172, 0.85)',
      text: isDark ? '#F0FDF4' : '#14532D',
      shadowGlow: isDark ? 'rgba(74, 222, 128, 0.15)' : 'rgba(22, 163, 74, 0.1)',
    },
    error: {
      icon: (
        <ErrorOutlineOutlinedIcon
          sx={{ fontSize: 18, color: isDark ? '#F87171' : '#DC2626', flexShrink: 0 }}
        />
      ),
      bg: isDark ? 'rgba(40, 20, 24, 0.85)' : 'rgba(254, 242, 242, 0.92)',
      border: isDark ? 'rgba(248, 113, 113, 0.35)' : 'rgba(254, 202, 202, 0.85)',
      text: isDark ? '#FEF2F2' : '#7F1D1D',
      shadowGlow: isDark ? 'rgba(248, 113, 113, 0.15)' : 'rgba(220, 38, 38, 0.1)',
    },
    warning: {
      icon: (
        <WarningAmberOutlinedIcon
          sx={{ fontSize: 18, color: isDark ? '#FBBF24' : '#D97706', flexShrink: 0 }}
        />
      ),
      bg: isDark ? 'rgba(40, 32, 18, 0.85)' : 'rgba(255, 251, 235, 0.92)',
      border: isDark ? 'rgba(251, 191, 36, 0.35)' : 'rgba(253, 230, 138, 0.85)',
      text: isDark ? '#FFFBEB' : '#78350F',
      shadowGlow: isDark ? 'rgba(251, 191, 36, 0.15)' : 'rgba(217, 119, 6, 0.1)',
    },
    processing: {
      icon: (
        <CircularProgress
          size={16}
          thickness={4.5}
          sx={{ color: isDark ? '#38BDF8' : '#0284C7', flexShrink: 0 }}
        />
      ),
      bg: isDark ? 'rgba(15, 28, 42, 0.85)' : 'rgba(240, 249, 255, 0.92)',
      border: isDark ? 'rgba(56, 189, 248, 0.35)' : 'rgba(186, 230, 253, 0.85)',
      text: isDark ? '#F0F9FF' : '#0C4A6E',
      shadowGlow: isDark ? 'rgba(56, 189, 248, 0.15)' : 'rgba(2, 132, 199, 0.1)',
    },
    info: {
      icon: (
        <InfoOutlinedIcon
          sx={{ fontSize: 18, color: isDark ? '#38BDF8' : '#0284C7', flexShrink: 0 }}
        />
      ),
      bg: isDark ? 'rgba(15, 28, 42, 0.85)' : 'rgba(240, 249, 255, 0.92)',
      border: isDark ? 'rgba(56, 189, 248, 0.35)' : 'rgba(186, 230, 253, 0.85)',
      text: isDark ? '#F0F9FF' : '#0C4A6E',
      shadowGlow: isDark ? 'rgba(56, 189, 248, 0.15)' : 'rgba(2, 132, 199, 0.1)',
    },
  }

  const currentConfig = severityConfigs[severity] || severityConfigs.info

  return (
    <Snackbar
      open={open}
      autoHideDuration={autoHideDuration}
      onClose={onClose}
      anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
      slots={{ transition: SlideTransition }}
      sx={{
        top: { xs: 16, sm: 24 },
        zIndex: 2000,
      }}
    >
      <Box
        role="status"
        aria-live="polite"
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.25,
          py: 0.9,
          px: 1.8,
          borderRadius: '12px',
          backgroundColor: currentConfig.bg,
          backdropFilter: 'blur(12px) saturate(180%)',
          WebkitBackdropFilter: 'blur(12px) saturate(180%)',
          border: `1px solid ${currentConfig.border}`,
          boxShadow: `0 8px 30px rgba(0, 0, 0, 0.18), 0 0 16px ${currentConfig.shadowGlow}`,
          maxWidth: '92vw',
          width: 'auto',
          minWidth: 260,
        }}
      >
        {currentConfig.icon}

        <Typography
          variant="body2"
          sx={{
            fontSize: '0.84rem',
            fontWeight: 600,
            color: currentConfig.text,
            lineHeight: 1.4,
            flexGrow: 1,
            userSelect: 'none',
          }}
        >
          {message}
        </Typography>

        {action && (
          <Box sx={{ ml: 0.5, flexShrink: 0 }}>
            {action}
          </Box>
        )}

        <IconButton
          size="small"
          onClick={onClose}
          aria-label="Dismiss notification"
          sx={{
            color: currentConfig.text,
            p: 0.4,
            opacity: 0.75,
            flexShrink: 0,
            '&:hover': {
              opacity: 1,
              backgroundColor: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.05)',
            },
          }}
        >
          <CloseIcon sx={{ fontSize: 15 }} />
        </IconButton>
      </Box>
    </Snackbar>
  )
}
