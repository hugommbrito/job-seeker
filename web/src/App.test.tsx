import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { api, onUnauthorized } from "@/api/client";
import { App } from "@/App";
import { endSession } from "@/auth/session";
import { empty, json, serve } from "@/test/server";

const MEMBER = { email: "person@example.test", role: "member" };
const PROFILE = {
  timezone: "America/Toronto",
  hard: { workplace_types: [], locations: [], salary_floor: null, seniority: [], employment_types: [], max_commute_km: null },
  notify: {
    quiet_hours: { start: "22:00:00", end: "08:00:00" },
    follow_up_after_days: 14,
    remind_next_action: true,
    remind_decision_due: true,
    remind_quiet: true,
  },
  home: null,
  onboarded: true,
};

function renderApp(path = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const unsubscribe = onUnauthorized(() => endSession(queryClient));
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { queryClient, unsubscribe };
}

async function signIn(password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), MEMBER.email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}

describe("App", () => {
  it("shows the sign-in form to a visitor, whatever the path", async () => {
    serve({ "GET /api/auth/me": () => json(401, { detail: "Unauthorized" }) });
    renderApp("/applications/7");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("opens on the board for someone already signed in", async () => {
    serve({
      "GET /api/auth/me": () => json(200, MEMBER),
      "GET /api/notifications": () => json(200, { unread: 0, items: [] }),
      "GET /api/profile": () => json(200, PROFILE),
      "GET /api/applications": () => json(200, []),
    });
    renderApp();
    expect(await screen.findByText("No applications yet")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Board" })).toBeInTheDocument();
    expect(screen.getByText(MEMBER.email)).toBeInTheDocument();
  });

  it("signs in, then out", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/auth/me": () => json(401, { detail: "Unauthorized" }),
      "GET /api/auth/options": () => json(200, { demo_login: false }),
      "GET /api/notifications": () => json(200, { unread: 0, items: [] }),
      "POST /api/auth/login": () => json(200, MEMBER),
      "GET /api/profile": () => json(200, PROFILE),
      "GET /api/applications": () => json(200, []),
      "POST /api/auth/logout": () => empty(),
    });
    renderApp();

    const user = await signIn("a long enough password");
    expect(await screen.findByText("No applications yet")).toBeInTheDocument();
    const login = requests.find((request) => request.url.endsWith("/api/auth/login"));
    expect(await login?.json()).toEqual({ email: MEMBER.email, password: "a long enough password" });

    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("shows the server's reason when sign-in is refused", async () => {
    document.cookie = "csrftoken=token";
    serve({
      "GET /api/auth/me": () => json(401, { detail: "Unauthorized" }),
      "GET /api/auth/options": () => json(200, { demo_login: false }),
      "GET /api/notifications": () => json(200, { unread: 0, items: [] }),
      "POST /api/auth/login": () => json(401, { detail: "Email or password is incorrect." }),
    });
    renderApp();
    await signIn("wrong");
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
  });

  it("returns to the sign-in form when the session expires", async () => {
    let signedIn = true;
    serve({
      "GET /api/auth/me": () => json(200, MEMBER),
      "GET /api/notifications": () => json(200, { unread: 0, items: [] }),
      "GET /api/profile": () => json(200, PROFILE),
      "GET /api/applications": () =>
        signedIn ? json(200, []) : json(401, { detail: "Unauthorized" }),
    });
    renderApp();
    expect(await screen.findByText("No applications yet")).toBeInTheDocument();

    signedIn = false;
    await api.GET("/api/applications");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("stays signed in after a 403", async () => {
    serve({
      "GET /api/auth/me": () => json(200, { email: "guest@example.test", role: "demo" }),
      "GET /api/notifications": () => json(200, { unread: 0, items: [] }),
      "GET /api/profile": () => json(200, { ...PROFILE, onboarded: false }),
      "GET /api/applications": () => json(403, { detail: "Not available to the demo account." }),
    });
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Not available to the demo account.",
    );
    expect(screen.getByText("Demo, read only")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("says so when the server cannot be reached", async () => {
    serve({ "GET /api/auth/me": () => json(500, { detail: "boom" }) });
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });

  it("starts a member who has not set up yet on the wizard", async () => {
    serve({
      "GET /api/auth/me": () => json(200, MEMBER),
      "GET /api/notifications": () => json(200, { unread: 0, items: [] }),
      "GET /api/profile": () => json(200, { ...PROFILE, onboarded: false }),
    });
    renderApp();
    expect(await screen.findByText("Setting up, step 1 of 5")).toBeInTheDocument();
  });

  it("offers the guest login when the server does, and signs in as the guest", async () => {
    document.cookie = "csrftoken=token";
    serve({
      "GET /api/auth/me": () => json(401, { detail: "Unauthorized" }),
      "GET /api/auth/options": () => json(200, { demo_login: true }),
      "POST /api/auth/demo": () => json(200, { email: "guest@demo.invalid", role: "demo" }),
      "GET /api/notifications": () => json(200, { unread: 0, items: [] }),
      "GET /api/profile": () => json(200, { ...PROFILE, onboarded: true }),
      "GET /api/applications": () => json(200, []),
    });
    renderApp();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Try the demo" }));
    expect(await screen.findByText("Demo, read only")).toBeInTheDocument();
  });

  it("has a page for paths it does not know", async () => {
    serve({ "GET /api/auth/me": () => json(200, MEMBER) });
    renderApp("/no/such/page");
    expect(await screen.findByText("Nothing here")).toBeInTheDocument();
  });
});
