import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { registerSW } from "virtual:pwa-register";

import App from "./App";
import "./index.css";
import "highlight.js/styles/github-dark.css";
import { AuthProvider } from "@/lib/AuthContext";
import { ThemeProvider } from "@/lib/theme";

// Makes the app installable ("添加到桌面") and serves the shell offline. The
// worker takes over as soon as it activates, so a new build lands on the next
// launch without interrupting the session in progress. No-op in dev.
registerSW({ immediate: true });

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
