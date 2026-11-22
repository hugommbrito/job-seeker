import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { api, onUnauthorized } from "@/api/client";
import { App } from "@/App";
import { endSession } from "@/auth/session";
import { empty, json, serve } from "@/test/server";

const MEMBER = { email: "person@example.test", role: "member" };

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const unsubscribe = onUnauthorized(() => endSession(queryClient));
  render(
    <QueryClientProvider client={queryClient}>
      <App />
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
  it("shows the sign-in form to a visitor", async () => {
    serve({ "GET /api/auth/me": () => json(401, { detail: "Unauthorized" }) });
    renderApp();
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("shows the empty app to someone already signed in", async () => {
    serve({
      "GET /api/auth/me": () => json(200, MEMBER),
      "GET /api/profile": () => json(200, { timezone: "America/Toronto" }),
    });
    renderApp();
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
    expect(screen.getByText(MEMBER.email)).toBeInTheDocument();
    expect(await screen.findByText("Timezone: America/Toronto")).toBeInTheDocument();
  });

  it("signs in, then out", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/auth/me": () => json(401, { detail: "Unauthorized" }),
      "POST /api/auth/login": () => json(200, MEMBER),
      "GET /api/profile": () => json(200, { timezone: "America/Toronto" }),
      "POST /api/auth/logout": () => empty(),
    });
    renderApp();

    const user = await signIn("a long enough password");
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
    const login = requests.find((request) => request.url.endsWith("/api/auth/login"));
    expect(await login?.json()).toEqual({ email: MEMBER.email, password: "a long enough password" });

    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("shows the server's reason when sign-in is refused", async () => {
    document.cookie = "csrftoken=token";
    serve({
      "GET /api/auth/me": () => json(401, { detail: "Unauthorized" }),
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
      "GET /api/profile": () =>
        signedIn ? json(200, { timezone: "UTC" }) : json(401, { detail: "Unauthorized" }),
    });
    renderApp();
    expect(await screen.findByText("Timezone: UTC")).toBeInTheDocument();

    signedIn = false;
    await api.GET("/api/profile");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("stays signed in after a 403", async () => {
    serve({
      "GET /api/auth/me": () => json(200, { email: "guest@example.test", role: "demo" }),
      "GET /api/profile": () => json(403, { detail: "Not available to the demo account." }),
    });
    renderApp();
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/Timezone/)).not.toBeInTheDocument());
    expect(screen.getByText("guest@example.test")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("says so when the server cannot be reached", async () => {
    serve({ "GET /api/auth/me": () => json(500, { detail: "boom" }) });
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });
});
