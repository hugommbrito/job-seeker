import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { BoardPage } from "@/pages/BoardPage";
import { application, GUEST, renderPage } from "@/test/render";
import { json, serve } from "@/test/server";

const ROWS = [
  application({ id: 1, company_name: "Alpha", stage: "saved" }),
  application({ id: 2, company_name: "Beta", stage: "interviews", next_action_due: "2020-01-01" }),
  application({ id: 3, company_name: "Gamma", stage: "applied", outcome: "rejected" }),
];

function column(name: string) {
  return screen.getByRole("region", { name });
}

describe("BoardPage", () => {
  it("puts open applications in their stage and closed ones apart", async () => {
    serve({ "GET /api/applications": () => json(200, ROWS) });
    renderPage(<BoardPage />);
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(within(column("Saved")).getByText("Alpha")).toBeInTheDocument();
    expect(within(column("Interviews")).getByText("Beta")).toBeInTheDocument();
    expect(within(column("Interviews")).getByText("Overdue")).toBeInTheDocument();
    expect(within(column("Closed")).getByText("Gamma")).toBeInTheDocument();
    expect(within(column("Closed")).getByText("Rejected")).toBeInTheDocument();
    expect(within(column("Applied")).queryByText("Gamma")).not.toBeInTheDocument();
  });

  it("moves a card from its menu", async () => {
    document.cookie = "csrftoken=token";
    let rows = ROWS;
    const requests = serve({
      "GET /api/applications": () => json(200, rows),
      "POST /api/applications/1/stage": async (request) => {
        const { stage } = (await request.json()) as { stage: string };
        rows = rows.map((row) => (row.id === 1 ? { ...row, stage } : row));
        return json(200, { ...rows[0], events: [], posting_snapshot: {} });
      },
    });
    renderPage(<BoardPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Move Alpha, Software Engineer" }));
    await user.click(await screen.findByRole("menuitem", { name: "Applied" }));

    expect(await within(column("Applied")).findByText("Alpha")).toBeInTheDocument();
    const move = requests.find((request) => request.url.endsWith("/api/applications/1/stage"));
    expect(await move?.json()).toEqual({ stage: "applied" });
  });

  it("closes a card with an outcome from its menu", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/applications": () => json(200, ROWS),
      "POST /api/applications/2/close": () =>
        json(200, { ...ROWS[1], outcome: "ghosted", events: [], posting_snapshot: {} }),
    });
    renderPage(<BoardPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Move Beta, Software Engineer" }));
    await user.click(await screen.findByRole("menuitem", { name: "Ghosted" }));
    const close = requests.find((request) => request.url.endsWith("/api/applications/2/close"));
    expect(await close?.json()).toEqual({ outcome: "ghosted" });
  });

  it("offers the guest nothing to change", async () => {
    serve({ "GET /api/applications": () => json(200, ROWS) });
    renderPage(<BoardPage />, { user: GUEST });
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add application/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Move / })).not.toBeInTheDocument();
  });

  it("says when there is nothing yet", async () => {
    serve({ "GET /api/applications": () => json(200, []) });
    renderPage(<BoardPage />);
    expect(await screen.findByText("No applications yet")).toBeInTheDocument();
  });

  it("creates an application from the dialog", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/applications": () => json(200, []),
      "POST /api/applications": () =>
        json(201, { ...application({ id: 9 }), events: [], posting_snapshot: {} }),
    });
    renderPage(<BoardPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Add application/ }));
    await user.type(screen.getByLabelText("Company"), "Example Corp");
    await user.type(screen.getByLabelText("Role"), "Analyst");
    await user.selectOptions(screen.getByLabelText("Outcome"), "rejected");
    await user.type(screen.getByLabelText("Closed on"), "2026-11-19");
    await user.click(screen.getByRole("button", { name: "Save" }));

    const create = requests.find(
      (request) => request.method === "POST" && request.url.endsWith("/api/applications"),
    );
    expect(await create?.json()).toMatchObject({
      company_name: "Example Corp",
      role_title: "Analyst",
      stage: "saved",
      outcome: "rejected",
      closed_on: "2026-11-19",
      applied_at: null,
    });
  });
});
