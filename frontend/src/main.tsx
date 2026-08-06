import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CssBaseline, ThemeProvider } from "@mui/material";

import App from "./App";
import { QueryPollingCoordinator } from "./QueryPollingCoordinator";
import { ApiFailure } from "./api/client";
import { configureQueryWindowSharing } from "./queryWindowSharing";
import { theme } from "./theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      gcTime: 300_000,
      refetchOnWindowFocus: true,
      retry: (failureCount, error) =>
        error instanceof ApiFailure && error.status >= 500 && failureCount < 1,
    },
    mutations: { retry: false },
  },
});

configureQueryWindowSharing(queryClient);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <QueryPollingCoordinator />
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
