import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";

import type { User } from "@/api/client";
import { UserContext } from "@/auth/user";
import { LocationProbe } from "@/test/LocationProbe";

export const MEMBER: User = { email: "person@example.test", role: "member" };
export const GUEST: User = { email: "guest@example.test", role: "demo" };

/** Render a page as the signed-in `user`, at `path`, matched against `route`. */
export function renderPage(
  page: ReactNode,
  { path = "/", route = "/", user = MEMBER }: { path?: string; route?: string; user?: User } = {},
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <UserContext.Provider value={user}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={route} element={page} />
            <Route path="*" element={<p>Elsewhere</p>} />
          </Routes>
          <LocationProbe />
        </MemoryRouter>
      </UserContext.Provider>
    </QueryClientProvider>,
  );
}

export function application(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    company_name: "Example Corp",
    role_title: "Software Engineer",
    stage: "saved",
    outcome: null,
    posting_url: "",
    location: "",
    source: "",
    notes: "",
    applied_at: null,
    last_interview_at: null,
    decision_due_at: null,
    next_action: "",
    next_action_due: null,
    last_activity_at: "2026-11-20",
    created_at: "2026-11-20T15:00:00Z",
    updated_at: "2026-11-20T15:00:00Z",
    closed_at: null,
    ...overrides,
  };
}
