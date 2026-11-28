import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ReviewCapturePage } from "@/pages/ReviewCapturePage";
import { renderPage } from "@/test/render";
import { json, serve } from "@/test/server";

const TEXT = "Senior Data Analyst\nExample Analytics Inc.\nSalary: $95,000 - $115,000 CAD";

const PROPOSAL = {
  title: "Senior Data Analyst",
  title_quote: "Senior Data Analyst",
  company: "Example Analytics Inc.",
  company_quote: "Example Analytics Inc.",
  location: null,
  location_quote: "",
  workplace_type: "unknown",
  workplace_quote: "",
  employment_type: "unknown",
  employment_quote: "",
  salary_min: 95000,
  salary_max: 115000,
  salary_currency: "CAD",
  salary_period: "unknown",
  salary_quote: "Salary: $95,000 - $115,000 CAD",
  application_deadline: null,
  deadline_quote: "",
  language: "en",
  ai_screening: "unknown",
  ai_screening_quote: "",
  existing_vacancy: "unknown",
  existing_vacancy_quote: "",
  issues: ["location"],
};

function capture(overrides: Record<string, unknown> = {}) {
  return {
    id: 3,
    source: "paste",
    url: "https://jobs.example.org/3",
    description_text: TEXT,
    extraction_status: "extracted",
    extraction_error: "",
    proposal: PROPOSAL,
    application_id: null,
    created_at: "2026-11-24T15:00:00Z",
    ...overrides,
  };
}

const ROUTE = { route: "/capture/:id", path: "/capture/3" };

describe("ReviewCapturePage", () => {
  it("prefills the fields from the reading and shows where each came from", async () => {
    serve({ "GET /api/captures/3": () => json(200, capture()) });
    renderPage(<ReviewCapturePage />, ROUTE);
    expect(await screen.findByLabelText("Role")).toHaveValue("Senior Data Analyst");
    expect(screen.getByLabelText("Company")).toHaveValue("Example Analytics Inc.");
    expect(screen.getByLabelText("From")).toHaveValue("95000");
    expect(screen.getByText("From the posting: “Salary: $95,000 - $115,000 CAD”")).toBeInTheDocument();
    // A value dropped by the server's quote check is flagged, not shown as found.
    expect(screen.getByText(/was not found in the posting/)).toBeInTheDocument();
  });

  it("saves the reviewed fields and opens the new application", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/captures/3": () => json(200, capture()),
      "POST /api/captures/3/save": () => json(201, { id: 12 }),
    });
    renderPage(<ReviewCapturePage />, ROUTE);
    const user = userEvent.setup();
    await user.clear(await screen.findByLabelText("Role"));
    await user.type(screen.getByLabelText("Role"), "Data Analyst");
    await user.selectOptions(screen.getByLabelText("Stage"), "applied");
    await user.click(screen.getByRole("button", { name: "Save as an application" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/applications/12"));
    const save = requests.find((request) => request.method === "POST");
    expect(await save?.json()).toMatchObject({
      title: "Data Analyst",
      company_name: "Example Analytics Inc.",
      salary_min: "95000",
      salary_currency: "CAD",
      stage: "applied",
      posting_url: "https://jobs.example.org/3",
      applied_at: null,
    });
  });

  it("waits while the posting is read, and can be filled in by hand meanwhile", async () => {
    serve({ "GET /api/captures/3": () => json(200, capture({ extraction_status: "pending", proposal: null })) });
    renderPage(<ReviewCapturePage />, ROUTE);
    expect(await screen.findByText("Reading the posting…")).toBeInTheDocument();
    expect(screen.queryByLabelText("Role")).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Fill in by hand instead" }));
    expect(screen.getByLabelText("Role")).toHaveValue("");
  });

  it("says why the posting was not read, and offers to try again", async () => {
    serve({
      "GET /api/captures/3": () =>
        json(200, capture({ extraction_status: "not_evaluated", extraction_error: "unavailable", proposal: null })),
    });
    renderPage(<ReviewCapturePage />, ROUTE);
    expect(await screen.findByText(/no model is configured on this server/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try reading it again" })).toBeInTheDocument();
    expect(screen.getByLabelText("Company")).toHaveValue("");
  });

  it("shows the posting as text", async () => {
    serve({
      "GET /api/captures/3": () => json(200, capture({ description_text: "<img src=x onerror=alert(1)>" })),
    });
    renderPage(<ReviewCapturePage />, ROUTE);
    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
