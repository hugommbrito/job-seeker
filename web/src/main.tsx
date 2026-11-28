import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { onUnauthorized } from "@/api/client";
import { App } from "@/App";
import { endSession } from "@/auth/session";

const queryClient = new QueryClient();

// Any 401, from any request, means the session is over: show the sign-in page.
onUnauthorized(() => endSession(queryClient));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
