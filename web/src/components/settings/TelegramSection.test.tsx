import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { TelegramSection } from "@/components/settings/TelegramSection";
import { json, serve } from "@/test/server";

function renderSection() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <TelegramSection />
    </QueryClientProvider>,
  );
}

const state = (telegram: Record<string, boolean>) => ({
  telegram: { available: true, linked: false, enabled: false, linking: false, ...telegram },
});

describe("TelegramSection", () => {
  it("says so when the server has no bot", async () => {
    serve({ "GET /api/channels": () => json(200, state({ available: false })) });
    renderSection();
    expect(await screen.findByText("Telegram is not set up on this server.")).toBeInTheDocument();
  });

  it("starts a link and shows where to press Start", async () => {
    document.cookie = "csrftoken=token";
    let linking = false;
    serve({
      "GET /api/channels": () => json(200, state({ linking })),
      "POST /api/channels/telegram/link": () => {
        linking = true;
        return json(200, { url: "https://t.me/example_bot?start=1_abc", expires_at: "2026-11-24T15:15:00Z" });
      },
    });
    renderSection();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Link Telegram" }));
    expect(await screen.findByRole("link", { name: "Open the bot in Telegram" })).toHaveAttribute(
      "href",
      "https://t.me/example_bot?start=1_abc",
    );
  });

  it("offers a test and unlinking once linked", async () => {
    serve({ "GET /api/channels": () => json(200, state({ linked: true, enabled: true })) });
    renderSection();
    expect(await screen.findByRole("button", { name: "Send a test" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unlink" })).toBeInTheDocument();
  });
});
