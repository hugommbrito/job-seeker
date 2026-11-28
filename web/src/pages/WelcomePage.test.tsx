import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { WelcomePage } from "@/pages/WelcomePage";
import { renderPage } from "@/test/render";
import { json, serve } from "@/test/server";

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
  onboarded: false,
};

describe("WelcomePage", () => {
  it("saves each step and finishes on the board", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/profile": () => json(200, PROFILE),
      "PATCH /api/profile": () => json(200, PROFILE),
      "GET /api/tracks": () => json(200, []),
      "POST /api/tracks": () => json(201, {}),
    });
    renderPage(<WelcomePage />, { route: "/welcome", path: "/welcome" });
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Save and continue" }));
    await user.type(await screen.findByLabelText("Track name"), "Data analysis");
    await user.type(screen.getByLabelText("Job titles"), "Data Analyst, BI Analyst");
    await user.click(screen.getByRole("button", { name: "Add track" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await user.click(await screen.findByLabelText("Remote"));
    await user.type(screen.getByLabelText("Lowest salary"), "90000");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));
    await user.click(await screen.findByRole("button", { name: "Save and continue" })); // home, left empty
    await user.clear(await screen.findByLabelText("No news for how many days"));
    await user.type(screen.getByLabelText("No news for how many days"), "10");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/board"));
    const bodies = await Promise.all(
      requests.filter((r) => r.method !== "GET").map(async (r) => [r.method, await r.json()]),
    );
    expect(bodies).toEqual([
      ["PATCH", { timezone: "America/Toronto" }],
      [
        "POST",
        { name: "Data analysis", target_titles: ["Data Analyst", "BI Analyst"], summary: "", active: true },
      ],
      [
        "PATCH",
        {
          hard: {
            workplace_types: ["remote"],
            locations: [],
            salary_floor: { amount: "90000", currency: "CAD", period: "year" },
            seniority: [],
            employment_types: [],
            max_commute_km: null,
          },
        },
      ],
      ["PATCH", { home: null }],
      [
        "PATCH",
        {
          notify: {
            quiet_hours: { start: "22:00", end: "08:00" },
            follow_up_after_days: 10,
            remind_next_action: true,
            remind_decision_due: true,
            remind_quiet: true,
          },
        },
      ],
      ["PATCH", { onboarded: true }],
    ]);
  });

  it("can be skipped, which still counts as set up", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/profile": () => json(200, PROFILE),
      "PATCH /api/profile": () => json(200, { ...PROFILE, onboarded: true }),
    });
    renderPage(<WelcomePage />, { route: "/welcome", path: "/welcome" });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Skip the rest" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/board"));
    expect(await requests.at(-1)?.json()).toEqual({ onboarded: true });
  });
});
