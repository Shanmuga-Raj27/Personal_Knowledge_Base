import React, { useState } from 'react'
import {
  Box,
  Container,
  Typography,
  Button,
  Grid,
  Card,
  CardContent,
  Chip,
  Stack,
  IconButton,
  useTheme,
  Divider,
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
import swanLogoUrl from '../assets/swan_drive_logo.svg'

export const SwanLogo = ({ size = 28 }) => (
  <Box
    component="img"
    src={swanLogoUrl}
    alt="Swan Drive"
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
  const [activeTab, setActiveTab] = useState('vault')

  const features = [
    {
      icon: <CloudQueueIcon sx={{ fontSize: 28, color: '#0284C7' }} />,
      title: 'Cloud Document Storage',
      desc: 'Secure cloud storage for your PDF, Word, Markdown, and tabular files with instant access.',
      badge: 'Storage',
    },
    {
      icon: <AutoAwesomeIcon sx={{ fontSize: 28, color: '#FF6B00' }} />,
      title: 'AI-Powered Document Organization',
      desc: 'Automatic metadata indexing, multi-tag categorization, and fast verification for all uploaded files.',
      badge: 'Intelligence',
    },
    {
      icon: <SearchIcon sx={{ fontSize: 28, color: '#0284C7' }} />,
      title: 'Intelligent Search',
      desc: 'Move beyond exact keywords. Find documents by intent, contextual relevance, and smart matching.',
      badge: 'Discovery',
    },
    {
      icon: <QuestionAnswerOutlinedIcon sx={{ fontSize: 28, color: '#FF6B00' }} />,
      title: 'Swan AI',
      desc: 'Select up to 5 documents and chat with Swan AI in real time. Accurate synthesis with strictly cited page references.',
      badge: 'Conversational',
    },
  ]

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* ── 1. NAVBAR ─────────────────────────────────────────── */}
      <Box
        component="header"
        sx={{
          position: 'sticky',
          top: 0,
          zIndex: 1100,
          backgroundColor: isDark ? 'rgba(10, 12, 16, 0.85)' : 'rgba(255, 255, 255, 0.9)',
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
            {/* Brand Logo */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, cursor: 'pointer' }}>
              <SwanLogo size={32} />
              <Typography
                variant="h6"
                sx={{
                  fontFamily: "Georgia, 'Times New Roman', Cambria, serif",
                  fontWeight: 700,
                  fontSize: '1.35rem',
                  letterSpacing: '-0.02em',
                  color: isDark ? '#FFFFFF' : '#0A0A0A',
                }}
              >
                Swan <Box component="span" sx={{ color: '#FF6B00' }}>Drive</Box>
              </Typography>
            </Box>

            {/* Nav actions */}
            <Stack direction="row" spacing={1.5} alignItems="center">
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

              <Button
                variant="text"
                onClick={onLoginClick}
                sx={{
                  color: isDark ? '#E2E8F0' : '#0A0A0A',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  px: 2,
                  '&:hover': {
                    backgroundColor: isDark ? 'rgba(255, 255, 255, 0.05)' : '#F1F5F9',
                  },
                }}
              >
                Sign In
              </Button>

              <Button
                variant="contained"
                onClick={onRegisterClick}
                sx={{
                  backgroundColor: '#0284C7', // Water Blue
                  color: '#FFFFFF',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  px: 2.5,
                  py: 0.85,
                  borderRadius: '8px',
                  '&:hover': {
                    backgroundColor: '#0369A1',
                  },
                }}
              >
                Get Started
              </Button>
            </Stack>
          </Box>
        </Container>
      </Box>

      {/* ── 2. HERO SECTION ─────────────────────────────────────────── */}
      <Box
        component="section"
        sx={{
          pt: { xs: 8, md: 12 },
          pb: { xs: 8, md: 10 },
          textAlign: 'center',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <Container maxWidth="md">
          {/* Tag pill */}
          <Chip
            icon={<AutoAwesomeIcon sx={{ fontSize: '15px !important', color: '#FF6B00' }} />}
            label="AI-Powered Cloud Storage Platform"
            size="small"
            sx={{
              mb: 3,
              px: 1,
              py: 2,
              borderRadius: '20px',
              backgroundColor: isDark ? 'rgba(255, 107, 0, 0.12)' : '#FFF5EE',
              border: `1px solid ${isDark ? 'rgba(255, 107, 0, 0.3)' : '#FFD8BF'}`,
              color: '#FF6B00',
              fontWeight: 700,
              fontSize: '0.8rem',
              letterSpacing: '0.02em',
            }}
          />

          {/* Serif Headline */}
          <Typography
            variant="h1"
            sx={{
              fontSize: { xs: '2.4rem', sm: '3.4rem', md: '4rem' },
              lineHeight: 1.15,
              color: isDark ? '#FFFFFF' : '#0A0A0A',
              mb: 2.5,
            }}
          >
            Intelligent Cloud Storage for Modern Knowledge
          </Typography>

          {/* Subtitle */}
          <Typography
            variant="body1"
            sx={{
              fontSize: { xs: '1rem', sm: '1.2rem' },
              color: theme.palette.text.secondary,
              maxWidth: 680,
              mx: 'auto',
              lineHeight: 1.6,
              mb: 4.5,
            }}
          >
            Swan Drive stores your PDF, Word, and text documents with secure cloud
            storage, instant intelligent search, and conversational Swan AI.
          </Typography>

          {/* Calls to Action */}
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            justifyContent="center"
            alignItems="center"
            sx={{ mb: 6 }}
          >
            <Button
              variant="contained"
              size="large"
              onClick={onRegisterClick}
              endIcon={<ArrowForwardIcon />}
              sx={{
                backgroundColor: '#0284C7', // Water blue
                color: '#FFFFFF',
                px: 3.5,
                py: 1.4,
                fontSize: '1rem',
                fontWeight: 700,
                borderRadius: '8px',
                width: { xs: '100%', sm: 'auto' },
                '&:hover': {
                  backgroundColor: '#0369A1',
                },
              }}
            >
              Start Free Today
            </Button>

            <Button
              variant="outlined"
              size="large"
              onClick={onLoginClick}
              sx={{
                borderColor: isDark ? '#2D3748' : '#CBD5E1',
                color: isDark ? '#FFFFFF' : '#0A0A0A',
                px: 3.5,
                py: 1.4,
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
              Sign In to Swan Drive
            </Button>
          </Stack>

          {/* Trust points */}
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={{ xs: 1.5, sm: 3 }}
            justifyContent="center"
            alignItems="center"
            sx={{ color: theme.palette.text.secondary, fontSize: '0.85rem' }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
              <CheckCircleOutlinedIcon sx={{ fontSize: 16, color: '#16A34A' }} />
              Secure Cloud Storage
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
              <CheckCircleOutlinedIcon sx={{ fontSize: 16, color: '#16A34A' }} />
              Intelligent Search
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
              <CheckCircleOutlinedIcon sx={{ fontSize: 16, color: '#16A34A' }} />
              Conversational Swan AI
            </Box>
          </Stack>
        </Container>
      </Box>

      {/* ── 3. PRODUCT PRESENTATION MOCKUP ─────────────────────────── */}
      <Box
        component="section"
        sx={{
          pb: { xs: 8, md: 12 },
          px: { xs: 2, sm: 3 },
        }}
      >
        <Container maxWidth="lg">
          {/* Tab selector */}
          <Box sx={{ display: 'flex', justifyContent: 'center', mb: 3 }}>
            <Box
              sx={{
                display: 'inline-flex',
                p: 0.5,
                borderRadius: '12px',
                backgroundColor: isDark ? '#141720' : '#F1F5F9',
                border: `1px solid ${theme.palette.divider}`,
              }}
            >
              <Button
                size="small"
                onClick={() => setActiveTab('vault')}
                startIcon={<FolderOutlinedIcon />}
                sx={{
                  px: 2.5,
                  py: 1,
                  borderRadius: '8px',
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  backgroundColor: activeTab === 'vault' ? (isDark ? '#1E2433' : '#FFFFFF') : 'transparent',
                  color: activeTab === 'vault' ? '#FF6B00' : theme.palette.text.secondary,
                  boxShadow: activeTab === 'vault' ? '0 2px 4px rgba(0,0,0,0.06)' : 'none',
                  '&:hover': {
                    backgroundColor: activeTab === 'vault' ? (isDark ? '#1E2433' : '#FFFFFF') : 'transparent',
                  },
                }}
              >
                My Drive
              </Button>
              <Button
                size="small"
                onClick={() => setActiveTab('kb')}
                startIcon={<AutoAwesomeIcon />}
                sx={{
                  px: 2.5,
                  py: 1,
                  borderRadius: '8px',
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  backgroundColor: activeTab === 'kb' ? (isDark ? '#1E2433' : '#FFFFFF') : 'transparent',
                  color: activeTab === 'kb' ? '#0284C7' : theme.palette.text.secondary,
                  boxShadow: activeTab === 'kb' ? '0 2px 4px rgba(0,0,0,0.06)' : 'none',
                  '&:hover': {
                    backgroundColor: activeTab === 'kb' ? (isDark ? '#1E2433' : '#FFFFFF') : 'transparent',
                  },
                }}
              >
                Swan AI
              </Button>
            </Box>
          </Box>

          {/* Mockup Frame */}
          <Card
            sx={{
              borderRadius: '16px',
              border: `1px solid ${theme.palette.divider}`,
              backgroundColor: theme.palette.background.paper,
              overflow: 'hidden',
              boxShadow: isDark
                ? '0 25px 50px -12px rgba(0, 0, 0, 0.7)'
                : '0 20px 40px -15px rgba(0, 0, 0, 0.08)',
            }}
          >
            {/* Mockup Window Header */}
            <Box
              sx={{
                px: 3,
                py: 1.8,
                borderBottom: `1px solid ${theme.palette.divider}`,
                backgroundColor: isDark ? '#12151D' : '#FBFBFC',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Box sx={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: '#EF4444' }} />
                <Box sx={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: '#F59E0B' }} />
                <Box sx={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: '#10B981' }} />
                <Typography
                  variant="caption"
                  sx={{ ml: 1.5, color: theme.palette.text.secondary, fontWeight: 600 }}
                >
                  app.swandrive.io / {activeTab === 'vault' ? 'my-drive' : 'swan-ai'}
                </Typography>
              </Box>
              <Chip
                label="Verified Cloud"
                size="small"
                sx={{
                  height: 20,
                  fontSize: '0.68rem',
                  fontWeight: 700,
                  backgroundColor: isDark ? 'rgba(16, 185, 129, 0.15)' : '#ECFDF5',
                  color: '#059669',
                  borderRadius: '4px',
                }}
              />
            </Box>

            {/* Mockup Content */}
            <CardContent sx={{ p: { xs: 2.5, sm: 4 } }}>
              {activeTab === 'vault' ? (
                <Box>
                  {/* Search Bar Preview */}
                  <Box
                    sx={{
                      p: 2,
                      mb: 3,
                      borderRadius: '10px',
                      border: `1px solid ${theme.palette.divider}`,
                      backgroundColor: isDark ? '#161922' : '#F8FAFC',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 2,
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, color: theme.palette.text.secondary, flexGrow: 1 }}>
                      <SearchIcon fontSize="small" />
                      <Typography variant="body2" sx={{ color: theme.palette.text.secondary }}>
                        Search documents by name, topic, or content...
                      </Typography>
                    </Box>
                    <Button
                      variant="contained"
                      size="small"
                      sx={{
                        backgroundColor: '#0284C7',
                        color: '#FFFFFF',
                        fontWeight: 700,
                        px: 2,
                      }}
                    >
                      Upload File
                    </Button>
                  </Box>

                  {/* Sample rows */}
                  <Stack spacing={1.5}>
                    {[
                      {
                        name: 'Q3 Financial Strategy & Cloud Architecture.pdf',
                        icon: <PictureAsPdfIcon sx={{ color: '#DC2626' }} />,
                        size: '2.4 MB',
                        desc: 'Quarterly financial forecasts and cloud migration milestone roadmap.',
                        tags: ['Finance', 'Cloud', 'Strategy'],
                        status: 'Indexed',
                        score: '98% Match',
                      },
                      {
                        name: 'Engineering Onboarding Manual.docx',
                        icon: <DescriptionIcon sx={{ color: '#0284C7' }} />,
                        size: '840 KB',
                        desc: 'Full developer setup instructions, credential rotation, and API specs.',
                        tags: ['Docs', 'Engineering'],
                        status: 'Indexed',
                        score: '91% Match',
                      },
                      {
                        name: 'Machine Learning RAG Pipeline Specs.md',
                        icon: <TextSnippetIcon sx={{ color: '#16A34A' }} />,
                        size: '128 KB',
                        desc: 'Detailed document processing, smart indexing, and synthesis prompts.',
                        tags: ['AI', 'Smart Index', 'Pipeline'],
                        status: 'Indexed',
                        score: '87% Match',
                      },
                    ].map((row, i) => (
                      <Box
                        key={i}
                        sx={{
                          p: 2,
                          borderRadius: '8px',
                          border: `1px solid ${theme.palette.divider}`,
                          backgroundColor: isDark ? '#141720' : '#FFFFFF',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 2,
                        }}
                      >
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.8, minWidth: 0, flexGrow: 1 }}>
                          {row.icon}
                          <Box sx={{ minWidth: 0 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.3 }}>
                              <Typography
                                variant="subtitle2"
                                sx={{
                                  fontWeight: 700,
                                  color: isDark ? '#F1F5F9' : '#0A0A0A',
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                }}
                              >
                                {row.name}
                              </Typography>
                              <Chip
                                label={row.status}
                                size="small"
                                sx={{
                                  height: 18,
                                  fontSize: '0.65rem',
                                  fontWeight: 700,
                                  backgroundColor: '#F0FDF4',
                                  color: '#166534',
                                  border: '1px solid #BBF7D0',
                                }}
                              />
                              <Chip
                                label={row.score}
                                size="small"
                                sx={{
                                  height: 18,
                                  fontSize: '0.65rem',
                                  fontWeight: 700,
                                  backgroundColor: isDark ? 'rgba(2, 132, 199, 0.15)' : '#F0F9FF',
                                  color: '#0284C7',
                                  border: '1px solid #BAE6FD',
                                }}
                              />
                            </Box>
                            <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
                              {row.desc} &bull; {row.size}
                            </Typography>
                          </Box>
                        </Box>
                        <Stack direction="row" spacing={0.8} sx={{ display: { xs: 'none', md: 'flex' } }}>
                          {row.tags.map((tag) => (
                            <Chip
                              key={tag}
                              label={tag}
                              size="small"
                              variant="outlined"
                              sx={{
                                height: 20,
                                fontSize: '0.68rem',
                                borderColor: theme.palette.divider,
                              }}
                            />
                          ))}
                        </Stack>
                      </Box>
                    ))}
                  </Stack>
                </Box>
              ) : (
                <Box sx={{ maxWidth: 720, mx: 'auto' }}>
                  {/* Context banner */}
                  <Box
                    sx={{
                      p: 1.5,
                      mb: 2.5,
                      borderRadius: '8px',
                      backgroundColor: isDark ? '#161922' : '#F8FAFC',
                      border: `1px solid ${theme.palette.divider}`,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1.5,
                    }}
                  >
                    <Typography variant="caption" sx={{ fontWeight: 700, color: theme.palette.text.secondary }}>
                      Grounding Context:
                    </Typography>
                    <Chip
                      icon={<PictureAsPdfIcon sx={{ fontSize: '14px !important', color: '#DC2626' }} />}
                      label="Q3 Financial Strategy.pdf"
                      size="small"
                      sx={{ height: 22, fontSize: '0.72rem', fontWeight: 600 }}
                    />
                    <Chip
                      icon={<DescriptionIcon sx={{ fontSize: '14px !important', color: '#0284C7' }} />}
                      label="Cloud Architecture.docx"
                      size="small"
                      sx={{ height: 22, fontSize: '0.72rem', fontWeight: 600 }}
                    />
                  </Box>

                  {/* Sample Query & Answer */}
                  <Stack spacing={2}>
                    <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <Box
                        sx={{
                          maxWidth: '75%',
                          p: 1.8,
                          borderRadius: '12px 12px 4px 12px',
                          backgroundColor: '#FF6B00', // Swan orange highlight
                          color: '#FFFFFF',
                        }}
                      >
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>
                          What are the primary cloud migration cost estimates for Q3 according to our docs?
                        </Typography>
                      </Box>
                    </Box>

                    <Box sx={{ display: 'flex', justifyContent: 'flex-start' }}>
                      <Box
                        sx={{
                          maxWidth: '85%',
                          p: 2,
                          borderRadius: '12px 12px 12px 4px',
                          border: `1px solid ${theme.palette.divider}`,
                          backgroundColor: isDark ? '#141720' : '#FFFFFF',
                        }}
                      >
                        <Typography variant="body2" sx={{ lineHeight: 1.6, mb: 1.5 }}>
                          Based on Section 4 of <strong>Q3 Financial Strategy.pdf [1]</strong>, the total projected
                          cloud infrastructure budget is allocated at \$142,000, with \$85,000 earmarked for secure document storage and intelligent indexing.
                        </Typography>
                        <Divider sx={{ my: 1 }} />
                        <Typography variant="caption" sx={{ fontWeight: 700, color: theme.palette.text.secondary, display: 'block', mb: 0.5 }}>
                          Sources:
                        </Typography>
                        <Chip
                          size="small"
                          label="Q3 Financial Strategy.pdf · Page 14"
                          variant="outlined"
                          sx={{ height: 22, fontSize: '0.72rem', fontWeight: 600 }}
                        />
                      </Box>
                    </Box>
                  </Stack>
                </Box>
              )}
            </CardContent>
          </Card>
        </Container>
      </Box>

      {/* ── 4. FEATURES SECTION ─────────────────────────────────────────── */}
      <Box
        component="section"
        sx={{
          py: { xs: 8, md: 12 },
          backgroundColor: isDark ? '#0C0E14' : '#F8FAFC',
          borderTop: `1px solid ${theme.palette.divider}`,
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Container maxWidth="lg">
          <Box sx={{ textAlign: 'center', mb: 7 }}>
            <Typography
              variant="overline"
              sx={{
                color: '#FF6B00',
                fontWeight: 700,
                letterSpacing: '0.08em',
                fontSize: '0.82rem',
              }}
            >
              Enterprise Capabilities
            </Typography>
            <Typography
              variant="h2"
              sx={{
                fontSize: { xs: '2rem', sm: '2.5rem' },
                color: isDark ? '#FFFFFF' : '#0A0A0A',
                mt: 1,
              }}
            >
              Designed for Speed, Accuracy & Scale
            </Typography>
          </Box>

          <Grid container spacing={3.5}>
            {features.map((item, idx) => (
              <Grid item xs={12} sm={6} md={3} key={idx}>
                <Card
                  sx={{
                    height: '100%',
                    borderRadius: '14px',
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: theme.palette.background.paper,
                    p: 1.5,
                    transition: 'transform 0.2s, border-color 0.2s',
                    '&:hover': {
                      transform: 'translateY(-4px)',
                      borderColor: '#FF6B00',
                    },
                  }}
                >
                  <CardContent sx={{ p: 2 }}>
                    <Box
                      sx={{
                        width: 48,
                        height: 48,
                        borderRadius: '12px',
                        backgroundColor: isDark ? 'rgba(255, 255, 255, 0.04)' : '#F1F5F9',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        mb: 2.5,
                      }}
                    >
                      {item.icon}
                    </Box>
                    <Typography
                      variant="h6"
                      sx={{
                        fontSize: '1.1rem',
                        fontWeight: 700,
                        color: isDark ? '#FFFFFF' : '#0A0A0A',
                        mb: 1,
                      }}
                    >
                      {item.title}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: theme.palette.text.secondary,
                        lineHeight: 1.6,
                        fontSize: '0.875rem',
                      }}
                    >
                      {item.desc}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      {/* ── 5. FINAL CALL TO ACTION ─────────────────────────────────────────── */}
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
              backgroundColor: isDark ? '#12151D' : '#0A0A0A',
              color: '#FFFFFF',
              border: `1px solid ${isDark ? '#262D3D' : '#1A1A1A'}`,
              textAlign: 'center',
            }}
          >
            <Typography
              variant="h3"
              sx={{
                fontSize: { xs: '1.8rem', sm: '2.4rem' },
                color: '#FFFFFF',
                mb: 2,
              }}
            >
              Get Started with Swan Drive
            </Typography>
            <Typography
              variant="body1"
              sx={{
                color: '#94A3B8',
                maxWidth: 540,
                mx: 'auto',
                mb: 4,
                lineHeight: 1.6,
              }}
            >
              Transform your static PDF, Word, and Markdown documents into an intelligent,
              queryable cloud repository in seconds.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="center">
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
                  borderColor: 'rgba(255, 255, 255, 0.3)',
                  color: '#FFFFFF',
                  fontWeight: 600,
                  fontSize: '1rem',
                  px: 4,
                  py: 1.4,
                  borderRadius: '8px',
                  '&:hover': {
                    borderColor: '#FF6B00',
                    backgroundColor: 'rgba(255, 107, 0, 0.1)',
                  },
                }}
              >
                Sign In
              </Button>
            </Stack>
          </Card>
        </Container>
      </Box>

      {/* ── 6. FOOTER ─────────────────────────────────────────── */}
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
                  fontFamily: "Georgia, 'Times New Roman', Cambria, serif",
                  fontWeight: 700,
                  color: isDark ? '#FFFFFF' : '#0A0A0A',
                }}
              >
                Swan <Box component="span" sx={{ color: '#FF6B00' }}>Drive</Box>
              </Typography>
            </Box>

            <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontWeight: 500 }}>
              &copy; {new Date().getFullYear()} Swan Drive. All rights reserved. Secure cloud storage & intelligent AI.
            </Typography>

            <Stack direction="row" spacing={3}>
              <Button
                variant="text"
                size="small"
                onClick={onLoginClick}
                sx={{ color: theme.palette.text.secondary, fontSize: '0.8rem', p: 0 }}
              >
                Sign In
              </Button>
              <Button
                variant="text"
                size="small"
                onClick={onRegisterClick}
                sx={{ color: theme.palette.text.secondary, fontSize: '0.8rem', p: 0 }}
              >
                Register
              </Button>
            </Stack>
          </Box>
        </Container>
      </Box>
    </Box>
  )
}
