import { createTheme } from '@mui/material/styles'

const SERIF_FONT = "'Cormorant Garamond', Georgia, 'Times New Roman', Cambria, serif"
const SANS_FONT = "'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

export const createAppTheme = (mode = 'light') => {
  const isDark = mode === 'dark'

  return createTheme({
    palette: {
      mode,
      primary: {
        main: '#FF6B00', // Swan Drive Orange (Brand Identity & Highlights)
        light: '#FF8833',
        dark: '#E65A00',
        contrastText: '#FFFFFF',
      },
      secondary: {
        main: '#0284C7', // Water Blue (Primary Interactive Buttons & Action Elements)
        light: '#38BDF8',
        dark: '#0369A1',
        contrastText: '#FFFFFF',
      },
      background: {
        default: isDark ? '#0A0C10' : '#FBFBFC',
        paper: isDark ? '#12151D' : '#FFFFFF',
      },
      text: {
        primary: isDark ? '#F1F5F9' : '#0A0A0A',
        secondary: isDark ? '#94A3B8' : '#64748B',
      },
      divider: isDark ? '#1E2430' : '#EAECEF',
      action: {
        hover: isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.03)',
        selected: isDark ? 'rgba(255, 107, 0, 0.12)' : 'rgba(255, 107, 0, 0.08)',
      },
    },
    typography: {
      fontFamily: SANS_FONT,
      h1: {
        fontFamily: SERIF_FONT,
        fontWeight: 700,
        letterSpacing: '-0.02em',
      },
      h2: {
        fontFamily: SERIF_FONT,
        fontWeight: 700,
        letterSpacing: '-0.02em',
      },
      h3: {
        fontFamily: SERIF_FONT,
        fontWeight: 700,
        letterSpacing: '-0.015em',
      },
      h4: {
        fontFamily: SERIF_FONT,
        fontWeight: 700,
        letterSpacing: '-0.01em',
      },
      h5: {
        fontFamily: SERIF_FONT,
        fontWeight: 700,
      },
      h6: {
        fontFamily: SERIF_FONT,
        fontWeight: 700,
      },
      subtitle1: {
        fontFamily: SANS_FONT,
        fontWeight: 600,
      },
      subtitle2: {
        fontFamily: SANS_FONT,
        fontWeight: 600,
      },
      body1: {
        fontFamily: SANS_FONT,
      },
      body2: {
        fontFamily: SANS_FONT,
      },
      button: {
        fontFamily: SANS_FONT,
        textTransform: 'none',
        fontWeight: 600,
      },
    },
    shape: {
      borderRadius: 10,
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundColor: isDark ? '#0A0C10' : '#FBFBFC',
            color: isDark ? '#F1F5F9' : '#0A0A0A',
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundImage: 'none',
            boxShadow: 'none',
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            textTransform: 'none',
            borderRadius: '8px',
            fontWeight: 600,
            boxShadow: 'none',
            '&:hover': {
              boxShadow: 'none',
            },
          },
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: {
            borderRadius: '14px',
            border: `1px solid ${isDark ? '#262D3D' : '#EAECEF'}`,
            boxShadow: isDark
              ? '0 20px 25px -5px rgba(0, 0, 0, 0.6), 0 8px 10px -6px rgba(0, 0, 0, 0.6)'
              : '0 20px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.04)',
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: {
            borderColor: isDark ? '#1E2430' : '#EAECEF',
          },
        },
      },
    },
  })
}
