import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "dark",
    background: { default: "#0b1017", paper: "#101720" },
    primary: { main: "#58a8d8", contrastText: "#061018" },
    info: { main: "#69b9dc" },
    warning: { main: "#e0a458" },
    error: { main: "#e36c70" },
    success: { main: "#72b89a" },
    text: { primary: "#e7edf5", secondary: "#8f9cad" },
    divider: "#263140",
  },
  shape: { borderRadius: 4 },
  typography: {
    fontFamily: 'Inter, "Segoe UI", Arial, sans-serif',
    h1: { fontSize: "clamp(2rem, 4vw, 3.25rem)", fontWeight: 650, letterSpacing: "-0.045em" },
    h2: { fontSize: "1.35rem", fontWeight: 650, letterSpacing: "-0.02em" },
    h3: { fontSize: "1rem", fontWeight: 700 },
    button: { textTransform: "none", fontWeight: 750 },
    overline: { fontFamily: '"Cascadia Mono", Consolas, monospace', fontWeight: 700, letterSpacing: "0.12em" },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { minWidth: 320, fontVariantNumeric: "tabular-nums" },
        "*:focus-visible": { outline: "3px solid #79c7f6", outlineOffset: 2 },
        "@media (prefers-reduced-motion: reduce)": {
          "*, *::before, *::after": { animationDuration: "0.01ms !important", transitionDuration: "0.01ms !important" },
        },
      },
    },
    MuiPaper: { defaultProps: { elevation: 0 } },
    MuiButton: { styleOverrides: { root: { minHeight: 40, boxShadow: "none" } } },
    MuiChip: { styleOverrides: { root: { borderRadius: 3, fontWeight: 750 } } },
    MuiAlert: { styleOverrides: { root: { borderRadius: 3, borderLeftWidth: 3, borderLeftStyle: "solid" } } },
    MuiDrawer: { styleOverrides: { paper: { backgroundImage: "none", borderColor: "#263140" } } },
  },
});
