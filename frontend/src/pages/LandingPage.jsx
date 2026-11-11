import React, { useState } from 'react'
import {
  Box,
  Container,
  Typography,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  IconButton,
  useTheme,
  Divider,
  Collapse,
  Tooltip,
} from '@mui/material'
import CloudQueueIcon from '@mui/icons-material/CloudQueue'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import SearchIcon from '@mui/icons-material/Search'
import SecurityIcon from '@mui/icons-material/Security'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import CheckCircleOutlinedIcon from '@mui/icons-material/CheckCircleOutlined'
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined'
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined'
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf'
import DescriptionIcon from '@mui/icons-material/Description'
import TextSnippetIcon from '@mui/icons-material/TextSnippet'
import FolderOutlinedIcon from '@mui/icons-material/FolderOutlined'
import QuestionAnswerOutlinedIcon from '@mui/icons-material/QuestionAnswerOutlined'
import MenuIcon from '@mui/icons-material/Menu'
import CloseIcon from '@mui/icons-material/Close'
import StorageIcon from '@mui/icons-material/Storage'
import LockOutlinedIcon from '@mui/icons-material/LockOutlined'
import LayersOutlinedIcon from '@mui/icons-material/LayersOutlined'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import swanLogoUrl from '../assets/swan_drive_logo.svg'

export const SwanLogo = ({ size = 28 }) => (
  <Box
    component="img"
    src={swanLogoUrl}
    alt="Swan Drive Logo"
    sx={{
      width: size,
      height: size,
      borderRadius: `${Math.max(4, Math.round(size * 0.18))}px`,
      display: 'inline-block',
      flexShrink: 0,
      objectFit: 'contain',
    }}
  />
)

export default function LandingPage({ onLoginClick, onRegisterClick, themeMode, onToggleTheme }) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const scrollToSection = (id) => {
    setMobileMenuOpen(false)
    const element = document.getElementById(id)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' })
    }
  }

  const features = [
    {
      icon: <StorageIcon sx={{ fontSize: 26, color: '#0284C7' }} />,
      title: 'Document Management',
      desc: 'Organize, view, and manage documents (.pdf, .docx, .md, .txt, .csv, .xlsx) in a centralized workspace.',
      status: 'Implemented',
    },
    {
      icon: <CloudQueueIcon sx={{ fontSize: 26, color: '#0284C7' }} />,
      title: 'Cloud Storage Integration',
      desc: 'Direct cloud storage uploads via secure presigned endpoints with automated file verification.',
      status: 'Implemented',
    },
    {
      icon: <AutoAwesomeIcon sx={{ fontSize: 26, color: '#FF6B00' }} />,
      title: 'AI-Assisted Document Interaction',
      desc: 'Ask questions about selected documents. Swan AI provides answers synthesized strictly from verified text.',
      status: 'Implemented',
    },
    {
      icon: <LockOutlinedIcon sx={{ fontSize: 26, color: '#16A34A' }} />,
      title: 'Secure Authentication',
      desc: 'JWT-based token authentication with tenant-isolated data access for each user.',
      status: 'Implemented',
    },
    {
      icon: <LayersOutlinedIcon sx={{ fontSize: 26, color: '#FF6B00' }} />,
      title: 'Modern Document Workspace',
      desc: 'Fast metadata indexing, keyword and intent search, responsive layout, and dark/light mode.',
      status: 'Implemented',
    },
  ]

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* ── 1. HEADER / NAVIGATION ─────────────────────────── */}
      <Box
        component="header"
        sx={{
          position: 'sticky',
          top: 0,
          zIndex: 1100,
          backgroundColor: isDark ? 'rgba(10, 12, 16, 0.88)' : 'rgba(255, 255, 255, 0.92)',
          backdropFilter: 'blur(10px)',
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Container maxWidth="lg">
          <Box
            sx={{
              height: 68,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            {/* Brand Logo & Beta Badge */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <Box
                sx={{ display: 'flex', alignItems: 'center', gap: 1.2, cursor: 'pointer' }}
                onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
              >
                <SwanLogo size={32} />
                <Typography
                  variant="h6"
                  sx={{
                    fontFamily: "'Cormorant Garamond', Georgia, serif",
                    fontWeight: 600,
                    fontSize: '1.55rem',
                    letterSpacing: '0.01em',
                    color: isDark ? '#FFFFFF' : '#0A0A0A',
                    display: 'flex',
                    alignItems: 'center',
                    lineHeight: 1,
                  }}
                >
                  Swan Drive
                </Typography>
              </Box>

              {/* Beta Badge with Tooltip */}
              <Tooltip
                title="Swan Drive is currently in beta Version."
                arrow
              >
                <Chip
                  label="Beta"
                  size="small"
                  sx={{
                    height: 20,
                    fontSize: '0.7rem',
                    fontWeight: 400,
                    letterSpacing: '0.02em',
                    backgroundColor: '#DC2626',
                    color: '#FFFFFF',
                    borderRadius: '6px',
                    cursor: 'help',
                  }}
                />
              </Tooltip>
            </Box>

            {/* Desktop Navigation Links */}
            <Box
              component="nav"
              aria-label="Product navigation"
              sx={{
                display: { xs: 'none', md: 'flex' },
                alignItems: 'center',
                gap: 3,
              }}
            >
              <Button
                variant="text"
                onClick={() => scrollToSection('my-drive')}
                sx={{
                  color: theme.palette.text.secondary,
                  fontWeight: 600,
                  fontSize: '0.88rem',
                  '&:hover': { color: isDark ? '#FFFFFF' : '#0A0A0A' },
                }}
              >
                My Drive
              </Button>
              <Button
                variant="text"
                onClick={() => scrollToSection('swan-ai')}
                sx={{
                  color: theme.palette.text.secondary,
                  fontWeight: 600,
                  fontSize: '0.88rem',
                  '&:hover': { color: isDark ? '#FFFFFF' : '#0A0A0A' },
                }}
              >
                Swan AI
              </Button>
              <Button
                variant="text"
                onClick={() => scrollToSection('features')}
                sx={{
                  color: theme.palette.text.secondary,
                  fontWeight: 600,
                  fontSize: '0.88rem',
                  '&:hover': { color: isDark ? '#FFFFFF' : '#0A0A0A' },
                }}
              >
                Features
              </Button>
            </Box>

            {/* Nav actions (Auth buttons & Theme toggle) */}
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
              {/* Theme toggle */}
              {onToggleTheme && (
                <IconButton
                  onClick={onToggleTheme}
                  size="small"
                  aria-label="Toggle light/dark theme"
                  sx={{
                    color: theme.palette.text.secondary,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: '8px',
                    p: 0.9,
                    '&:hover': {
                      backgroundColor: isDark ? 'rgba(255, 255, 255, 0.05)' : '#F8FAFC',
                      color: isDark ? '#FFFFFF' : '#0A0A0A',
                    },
                  }}
                >
                  {isDark ? <LightModeOutlinedIcon fontSize="small" /> : <DarkModeOutlinedIcon fontSize="small" />}
                </IconButton>
              )}

              {/* Login Button */}
              <Button
                variant="text"
                onClick={onLoginClick}
                sx={{
                  color: isDark ? '#E2E8F0' : '#0A0A0A',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  px: 2,
                  display: { xs: 'none', sm: 'inline-flex' },
                  '&:hover': {
                    backgroundColor: isDark ? 'rgba(255, 255, 255, 0.05)' : '#F1F5F9',
                  },
                }}
              >
                Login
              </Button>

              {/* Create Account Button */}
              <Button
                variant="contained"
                onClick={onRegisterClick}
                sx={{
                  backgroundColor: '#0284C7', // Water Blue
                  color: '#FFFFFF',
                  fontWeight: 600,
                  fontSize: '0.88rem',
                  px: 2.2,
                  py: 0.85,
                  borderRadius: '8px',
                  display: { xs: 'none', sm: 'inline-flex' },
                  '&:hover': {
                    backgroundColor: '#0369A1',
                  },
                }}
              >
                Create Account
              </Button>

              {/* Mobile menu toggle */}
              <IconButton
                onClick={() => setMobileMenuOpen((prev) => !prev)}
                aria-label="Toggle navigation menu"
                sx={{
                  display: { xs: 'inline-flex', md: 'none' },
                  color: theme.palette.text.secondary,
                  border: `1px solid ${theme.palette.divider}`,
                  borderRadius: '8px',
                  p: 0.8,
                }}
              >
                {mobileMenuOpen ? <CloseIcon fontSize="small" /> : <MenuIcon fontSize="small" />}
              </IconButton>
            </Stack>
          </Box>

          {/* Mobile Navigation Drawer Collapse */}
          <Collapse in={mobileMenuOpen} timeout="auto" unmountOnExit>
            <Box
              sx={{
                py: 2,
                borderTop: `1px solid ${theme.palette.divider}`,
                display: { xs: 'flex', md: 'none' },
                flexDirection: 'column',
                gap: 1.5,
              }}
            >
              <Button
                fullWidth
                variant="text"
                onClick={() => scrollToSection('my-drive')}
                sx={{ justifyContent: 'flex-start', color: theme.palette.text.primary, fontWeight: 600 }}
              >
                My Drive
              </Button>
              <Button
                fullWidth
                variant="text"
                onClick={() => scrollToSection('swan-ai')}
                sx={{ justifyContent: 'flex-start', color: theme.palette.text.primary, fontWeight: 600 }}
              >
                Swan AI
              </Button>
              <Button
                fullWidth
                variant="text"
                onClick={() => scrollToSection('features')}
                sx={{ justifyContent: 'flex-start', color: theme.palette.text.primary, fontWeight: 600 }}
              >
                Product Features
              </Button>
              <Divider sx={{ my: 0.5 }} />
              <Stack direction="row" spacing={1.5} sx={{ pt: 0.5 }}>
                <Button
                  fullWidth
                  variant="outlined"
                  onClick={onLoginClick}
                  sx={{ borderColor: theme.palette.divider, color: theme.palette.text.primary, fontWeight: 600 }}
                >
                  Login
                </Button>
                <Button
                  fullWidth
                  variant="contained"
                  onClick={onRegisterClick}
                  sx={{ backgroundColor: '#0284C7', color: '#FFFFFF', fontWeight: 600, '&:hover': { backgroundColor: '#0369A1' } }}
                >
                  Create Account
                </Button>
              </Stack>
            </Box>
          </Collapse>
        </Container>
      </Box>

      {/* ── 2. HERO SECTION ─────────────────────────── */}
      <Box
        component="section"
        sx={{
          pt: { xs: 8, md: 14 },
          pb: { xs: 8, md: 14 },
          position: 'relative',
        }}
      >
        <Container maxWidth="lg">
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column-reverse', md: 'row' },
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: { xs: 6, md: 8 },
            }}
          >
            {/* Left Side: Product Name & Action Buttons */}
            <Box sx={{ flex: 1, textAlign: { xs: 'center', md: 'left' } }}>
              <Typography
                variant="h1"
                component="h1"
                sx={{
                  fontFamily: "'Cormorant Garamond', Georgia, serif",
                  fontWeight: 600,
                  fontSize: { xs: '3.6rem', sm: '4.8rem', md: '6.2rem' },
                  lineHeight: 1.05,
                  letterSpacing: '-0.02em',
                  color: isDark ? '#FFFFFF' : '#0A0A0A',
                  mb: 4.5,
                }}
              >
                Swan Drive
              </Typography>

              {/* Calls to Action */}
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={2}
                sx={{
                  justifyContent: { xs: 'center', md: 'flex-start' },
                  alignItems: 'center',
                }}
              >
                <Button
                  variant="contained"
                  size="large"
                  onClick={onRegisterClick}
                  endIcon={<ArrowForwardIcon />}
                  sx={{
                    backgroundColor: '#0284C7', // Water Blue
                    color: '#FFFFFF',
                    px: 4,
                    py: 1.5,
                    fontSize: '1rem',
                    fontWeight: 700,
                    borderRadius: '8px',
                    width: { xs: '100%', sm: 'auto' },
                    '&:hover': {
                      backgroundColor: '#0369A1',
                    },
                  }}
                >
                  Create Account
                </Button>

                <Button
                  variant="outlined"
                  size="large"
                  onClick={onLoginClick}
                  sx={{
                    borderColor: isDark ? '#2D3748' : '#CBD5E1',
                    color: isDark ? '#FFFFFF' : '#0A0A0A',
                    px: 4,
                    py: 1.5,
                    fontSize: '1rem',
                    fontWeight: 600,
                    borderRadius: '8px',
                    width: { xs: '100%', sm: 'auto' },
                    '&:hover': {
                      borderColor: '#FF6B00',
                      backgroundColor: isDark ? 'rgba(255, 107, 0, 0.08)' : '#FFF5EE',
                    },
                  }}
                >
                  Login
                </Button>
              </Stack>
            </Box>

            {/* Right Side: Big Swan Logo */}
            <Box
              sx={{
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Box
                component="img"
                src={swanLogoUrl}
                alt="Swan Drive Logo"
                sx={{
                  width: { xs: 220, sm: 300, md: 380 },
                  height: { xs: 220, sm: 300, md: 380 },
                  objectFit: 'contain',
                  filter: isDark
                    ? 'drop-shadow(0 20px 40px rgba(0, 0, 0, 0.6))'
                    : 'drop-shadow(0 15px 30px rgba(0, 0, 0, 0.08))',
                }}
              />
            </Box>
          </Box>
        </Container>
      </Box>


      {/* ── 4. PRODUCT SECTION: MY DRIVE ─────────────────────────── */}
      <Box
        id="my-drive"
        component="section"
        sx={{
          py: { xs: 8, md: 10 },
          backgroundColor: isDark ? '#0C0E14' : '#F8FAFC',
          borderTop: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 6 }}>
            <Typography
              variant="overline"
              sx={{ color: '#0284C7', fontWeight: 700, letterSpacing: '0.08em', fontSize: '0.82rem' }}
            >
              Document Workspace
            </Typography>
            <Typography variant="h2" sx={{ fontSize: { xs: '1.9rem', sm: '2.4rem' }, mt: 0.5, mb: 1.5 }}>
              My Drive – File and Document Management
            </Typography>
            <Typography variant="body1" sx={{ color: theme.palette.text.secondary, maxWidth: 650, mx: 'auto' }}>
              Organize and access supported documents with verified cloud storage, custom metadata tags, and dynamic status tracking.
            </Typography>
          </Box>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' },
              gap: 3,
            }}
          >
            <Card
              sx={{
                borderRadius: '14px',
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: theme.palette.background.paper,
                p: 1,
              }}
            >
              <CardContent>
                <Box
                  sx={{
                    width: 44,
                    height: 44,
                    borderRadius: '10px',
                    backgroundColor: isDark ? 'rgba(2, 132, 199, 0.15)' : '#F0F9FF',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    mb: 2,
                    color: '#0284C7',
                  }}
                >
                  <FolderOutlinedIcon />
                </Box>
                <Typography variant="h6" sx={{ fontSize: '1.1rem', fontWeight: 700, mb: 1 }}>
                  Organize & Manage Documents
                </Typography>
                <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.6 }}>
                  Keep your knowledge structured with custom titles, descriptions, and searchable multi-tag labels.
                </Typography>
              </CardContent>
            </Card>

            <Card
              sx={{
                borderRadius: '14px',
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: theme.palette.background.paper,
                p: 1,
              }}
            >
              <CardContent>
                <Box
                  sx={{
                    width: 44,
                    height: 44,
                    borderRadius: '10px',
                    backgroundColor: isDark ? 'rgba(22, 163, 74, 0.15)' : '#F0FDF4',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    mb: 2,
                    color: '#16A34A',
                  }}
                >
                  <CloudQueueIcon />
                </Box>
                <Typography variant="h6" sx={{ fontSize: '1.1rem', fontWeight: 700, mb: 1 }}>
                  Upload Supported Formats
                </Typography>
                <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.6 }}>
                  Upload PDF, Word (.docx), Markdown (.md), plain text (.txt), and tabular files (.csv, .xlsx) via presigned cloud storage.
                </Typography>
              </CardContent>
            </Card>

            <Card
              sx={{
                borderRadius: '14px',
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: theme.palette.background.paper,
                p: 1,
              }}
            >
              <CardContent>
                <Box
                  sx={{
                    width: 44,
                    height: 44,
                    borderRadius: '10px',
                    backgroundColor: isDark ? 'rgba(255, 107, 0, 0.15)' : '#FFF5EE',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    mb: 2,
                    color: '#FF6B00',
                  }}
                >
                  <AutoAwesomeIcon />
                </Box>
                <Typography variant="h6" sx={{ fontSize: '1.1rem', fontWeight: 700, mb: 1 }}>
                  Dynamic Processing Status
                </Typography>
                <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.6 }}>
                  View real-time document indexing status without manual page refreshes. Status updates dynamically as processing completes.
                </Typography>
              </CardContent>
            </Card>
          </Box>
        </Container>
      </Box>

      {/* ── 5. PRODUCT SECTION: SWAN AI ─────────────────────────── */}
      <Box
        id="swan-ai"
        component="section"
        sx={{
          py: { xs: 8, md: 10 },
          borderTop: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 6 }}>
            <Typography
              variant="overline"
              sx={{ color: '#FF6B00', fontWeight: 700, letterSpacing: '0.08em', fontSize: '0.82rem' }}
            >
              Document Intelligence
            </Typography>
            <Typography variant="h2" sx={{ fontSize: { xs: '1.9rem', sm: '2.4rem' }, mt: 0.5, mb: 1.5 }}>
              Swan AI – Grounded Conversational Assistant
            </Typography>
            <Typography variant="body1" sx={{ color: theme.palette.text.secondary, maxWidth: 650, mx: 'auto' }}>
              Select documents in My Drive and ask specific questions. Swan AI synthesizes answers grounded strictly in your document text.
            </Typography>
          </Box>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' },
              gap: 3,
            }}
          >
            <Card
              sx={{
                borderRadius: '14px',
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: theme.palette.background.paper,
                p: 1,
              }}
            >
              <CardContent>
                <Box
                  sx={{
                    width: 44,
                    height: 44,
                    borderRadius: '10px',
                    backgroundColor: isDark ? 'rgba(255, 107, 0, 0.15)' : '#FFF5EE',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    mb: 2,
                    color: '#FF6B00',
                  }}
                >
                  <QuestionAnswerOutlinedIcon />
                </Box>
                <Typography variant="h6" sx={{ fontSize: '1.1rem', fontWeight: 700, mb: 1 }}>
                  Multi-Document Selection
                </Typography>
                <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.6 }}>
                  Choose up to 5 indexed documents as grounding context for your conversation in Swan AI.
                </Typography>
              </CardContent>
            </Card>

            <Card
              sx={{
                borderRadius: '14px',
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: theme.palette.background.paper,
                p: 1,
              }}
            >
              <CardContent>
                <Box
                  sx={{
                    width: 44,
                    height: 44,
                    borderRadius: '10px',
                    backgroundColor: isDark ? 'rgba(2, 132, 199, 0.15)' : '#F0F9FF',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    mb: 2,
                    color: '#0284C7',
                  }}
                >
                  <SearchIcon />
                </Box>
                <Typography variant="h6" sx={{ fontSize: '1.1rem', fontWeight: 700, mb: 1 }}>
                  Semantic Retrieval & Grounding
                </Typography>
                <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.6 }}>
                  Relevant document passages are extracted and verified before answer generation, preventing ungrounded hallucination.
                </Typography>
              </CardContent>
            </Card>

            <Card
              sx={{
                borderRadius: '14px',
                border: `1px solid ${theme.palette.divider}`,
                backgroundColor: theme.palette.background.paper,
                p: 1,
              }}
            >
              <CardContent>
                <Box
                  sx={{
                    width: 44,
                    height: 44,
                    borderRadius: '10px',
                    backgroundColor: isDark ? 'rgba(22, 163, 74, 0.15)' : '#F0FDF4',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    mb: 2,
                    color: '#16A34A',
                  }}
                >
                  <CheckCircleOutlinedIcon />
                </Box>
                <Typography variant="h6" sx={{ fontSize: '1.1rem', fontWeight: 700, mb: 1 }}>
                  Cited Page References
                </Typography>
                <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.6 }}>
                  Every answer provides citations linking back to original file names and specific page ranges.
                </Typography>
              </CardContent>
            </Card>
          </Box>
        </Container>
      </Box>

      {/* ── 6. PRODUCT SECTION: FEATURES ─────────────────────────── */}
      <Box
        id="features"
        component="section"
        sx={{
          py: { xs: 8, md: 10 },
          backgroundColor: isDark ? '#0C0E14' : '#F8FAFC',
          borderTop: `1px solid ${theme.palette.divider}`,
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 6 }}>
            <Typography
              variant="overline"
              sx={{ color: '#0284C7', fontWeight: 700, letterSpacing: '0.08em', fontSize: '0.82rem' }}
            >
              Core Capabilities
            </Typography>
            <Typography variant="h2" sx={{ fontSize: { xs: '1.9rem', sm: '2.4rem' }, mt: 0.5, mb: 1.5 }}>
              Implemented Product Features
            </Typography>
            <Typography variant="body1" sx={{ color: theme.palette.text.secondary, maxWidth: 650, mx: 'auto' }}>
              Reliable document workflows built on clean architecture and verified features.
            </Typography>
          </Box>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)' },
              gap: 3,
            }}
          >
            {features.map((item, idx) => (
              <Card
                key={idx}
                sx={{
                  borderRadius: '14px',
                  border: `1px solid ${theme.palette.divider}`,
                  backgroundColor: theme.palette.background.paper,
                  p: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                    <Box
                      sx={{
                        width: 44,
                        height: 44,
                        borderRadius: '10px',
                        backgroundColor: isDark ? 'rgba(255, 255, 255, 0.04)' : '#F1F5F9',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      {item.icon}
                    </Box>
                    <Chip
                      label={item.status}
                      size="small"
                      sx={{
                        height: 20,
                        fontSize: '0.65rem',
                        fontWeight: 700,
                        backgroundColor: isDark ? 'rgba(22, 163, 74, 0.15)' : '#F0FDF4',
                        color: '#16A34A',
                        border: '1px solid rgba(22, 163, 74, 0.25)',
                      }}
                    />
                  </Box>
                  <Typography variant="h6" sx={{ fontSize: '1.05rem', fontWeight: 700, mb: 1 }}>
                    {item.title}
                  </Typography>
                  <Typography variant="body2" sx={{ color: theme.palette.text.secondary, lineHeight: 1.6 }}>
                    {item.desc}
                  </Typography>
                </CardContent>
              </Card>
            ))}
          </Box>
        </Container>
      </Box>

      {/* ── 7. CALL TO ACTION ─────────────────────────── */}
      <Box
        component="section"
        sx={{
          py: { xs: 8, md: 10 },
          textAlign: 'center',
        }}
      >
        <Container maxWidth="md">
          <Card
            sx={{
              p: { xs: 4, sm: 6 },
              borderRadius: '20px',
              backgroundColor: isDark ? '#12151D' : '#FFFFFF',
              color: isDark ? '#FFFFFF' : '#0A0A0A',
              border: `1px solid ${isDark ? '#262D3D' : theme.palette.divider}`,
              boxShadow: isDark
                ? '0 10px 30px -10px rgba(0, 0, 0, 0.5)'
                : '0 10px 30px -10px rgba(0, 0, 0, 0.06)',
              textAlign: 'center',
            }}
          >
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: '1.8rem', sm: '2.4rem' },
                color: isDark ? '#FFFFFF' : '#0A0A0A',
                mb: 2,
              }}
            >
              Get Started with Swan Drive
            </Typography>
            <Typography
              variant="body1"
              sx={{
                color: theme.palette.text.secondary,
                maxWidth: 560,
                mx: 'auto',
                mb: 4,
                lineHeight: 1.65,
              }}
            >
              Manage your documents in Swan Drive with cloud storage, search, and conversational Swan AI.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ justifyContent: 'center' }}>
              <Button
                variant="contained"
                size="large"
                onClick={onRegisterClick}
                sx={{
                  backgroundColor: '#0284C7', // Water Blue
                  color: '#FFFFFF',
                  fontWeight: 700,
                  fontSize: '1rem',
                  px: 4,
                  py: 1.4,
                  borderRadius: '8px',
                  '&:hover': {
                    backgroundColor: '#0369A1',
                  },
                }}
              >
                Create Account
              </Button>
              <Button
                variant="outlined"
                size="large"
                onClick={onLoginClick}
                sx={{
                  borderColor: isDark ? 'rgba(255, 255, 255, 0.3)' : '#CBD5E1',
                  color: isDark ? '#FFFFFF' : '#0A0A0A',
                  fontWeight: 600,
                  fontSize: '1rem',
                  px: 4,
                  py: 1.4,
                  borderRadius: '8px',
                  '&:hover': {
                    borderColor: '#FF6B00',
                    backgroundColor: isDark ? 'rgba(255, 107, 0, 0.1)' : '#FFF5EE',
                  },
                }}
              >
                Login
              </Button>
            </Stack>
          </Card>
        </Container>
      </Box>

      {/* ── 8. FOOTER ─────────────────────────── */}
      <Box
        component="footer"
        sx={{
          mt: 'auto',
          py: 4,
          borderTop: `1px solid ${theme.palette.divider}`,
          backgroundColor: isDark ? '#0A0C10' : '#FFFFFF',
        }}
      >
        <Container maxWidth="lg">
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', sm: 'row' },
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 2,
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2 }}>
              <SwanLogo size={24} />
              <Typography
                variant="subtitle2"
                sx={{
                  fontFamily: "'Cormorant Garamond', Georgia, serif",
                  fontWeight: 600,
                  fontSize: '1.25rem',
                  letterSpacing: '0.01em',
                  color: isDark ? '#FFFFFF' : '#0A0A0A',
                  lineHeight: 1,
                }}
              >
                Swan Drive
              </Typography>
            </Box>

            <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontWeight: 500 }}>
              &copy; {new Date().getFullYear()} Swan Drive. All rights reserved. Document management & AI workspace.
            </Typography>

            <Stack direction="row" spacing={3}>
              <Button
                variant="text"
                size="small"
                onClick={onLoginClick}
                sx={{ color: theme.palette.text.secondary, fontSize: '0.8rem', p: 0 }}
              >
                Login
              </Button>
              <Button
                variant="text"
                size="small"
                onClick={onRegisterClick}
                sx={{ color: theme.palette.text.secondary, fontSize: '0.8rem', p: 0 }}
              >
                Create Account
              </Button>
            </Stack>
          </Box>
        </Container>
      </Box>
    </Box>
  )
}
