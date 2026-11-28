import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { NotificationsPage } from "@/pages/NotificationsPage";
import { renderPage } from "@/test/render";
import { empty, json, serve } from "@/test/server";

const ITEMS = [
  {
    id: 2,
    kind: "decision_due",
    title: "Decision overdue: Example Corp",
    body: "45 days since your last interview.",
    link: "/applications/7",
    created_at: "2026-11-24T15:00:00Z",
    read: false,
  },
  {
    id: 1,
    kind: "test",
    title: "Elsewhere",
    body: "",
    link: "https://elsewhere.example",
    created_at: "2026-11-23T15:00:00Z",
    read: true,
  },
];

describe("NotificationsPage", () => {
  it("lists notifications, links only inside the app, and marks them read", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/notifications": () => json(200, { unread: 1, items: ITEMS }),
      "POST /api/notifications/read": () => empty(),
    });
    renderPage(<NotificationsPage />, { route: "/notifications", path: "/notifications" });
    expect(await screen.findByText("Decision overdue: Example Corp")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: "Open" });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/applications/7");

    await userEvent.setup().click(screen.getByRole("button", { name: "Mark all as read" }));
    const read = requests.find((request) => request.method === "POST");
    expect(await read?.json()).toEqual({ ids: null });
  });
});
