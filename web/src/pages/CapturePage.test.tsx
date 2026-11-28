import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CapturePage } from "@/pages/CapturePage";
import { GUEST, renderPage } from "@/test/render";
import { json, serve } from "@/test/server";

const PENDING = {
  id: 3,
  source: "paste",
  url: "",
  description_text: "Senior Data Analyst at Example Analytics",
  extraction_status: "pending",
  extraction_error: "",
  proposal: null,
  application_id: null,
  created_at: "2026-11-24T15:00:00Z",
};

describe("CapturePage", () => {
  it("keeps the pasted text and opens its review", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/captures": () => json(200, []),
      "POST /api/captures": () => json(201, PENDING),
    });
    renderPage(<CapturePage />, { route: "/capture", path: "/capture" });
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Posting text"), "Senior Data Analyst at Example Analytics");
    await user.type(screen.getByLabelText(/Where it was posted/), "https://jobs.example.org/3");
    await user.click(screen.getByRole("button", { name: "Read the posting" }));

    expect(await screen.findByTestId("location")).toHaveTextContent("/capture/3");
    const create = requests.find((request) => request.method === "POST");
    expect(await create?.json()).toEqual({
      text: "Senior Data Analyst at Example Analytics",
      url: "https://jobs.example.org/3",
    });
  });

  it("lists postings that were pasted and not saved", async () => {
    serve({ "GET /api/captures": () => json(200, [PENDING]) });
    renderPage(<CapturePage />, { route: "/capture", path: "/capture" });
    expect(await screen.findByRole("link", { name: /Senior Data Analyst/ })).toHaveAttribute(
      "href",
      "/capture/3",
    );
  });

  it("offers the guest no form", async () => {
    serve({ "GET /api/captures": () => json(200, []) });
    renderPage(<CapturePage />, { route: "/capture", path: "/capture", user: GUEST });
    expect(screen.queryByLabelText("Posting text")).not.toBeInTheDocument();
  });
});
