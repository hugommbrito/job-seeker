import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApplicationPage } from "@/pages/ApplicationPage";
import { application, GUEST, renderPage } from "@/test/render";
import { json, serve } from "@/test/server";

const DETAIL = {
  ...application({
    id: 5,
    stage: "interviews",
    posting_url: "https://jobs.example.org/5",
    last_interview_at: "2026-03-10",
    decision_due_at: "2026-04-24",
    notes: "<script>not markup</script>",
  }),
  posting_snapshot: { description: "<b>Posting text</b> stays text" },
  contacts: [
    {
      id: 21,
      name: "Sam Recruiter",
      role: "Talent partner",
      email: "sam@example.org",
      phone: "",
      profile_url: "",
      notes: "",
      created_at: "2026-03-01T15:00:00Z",
    },
  ],
  documents: [
    {
      id: 31,
      kind: "cv",
      filename: "cv.pdf",
      content_type: "application/pdf",
      size: 2048,
      created_at: "2026-03-01T15:00:00Z",
    },
  ],
  events: [
    {
      id: 11,
      kind: "interview",
      occurred_on: "2026-03-10",
      text: "Panel",
      payload: {},
      editable: true,
      created_at: "2026-03-10T15:00:00Z",
    },
    {
      id: 10,
      kind: "stage_changed",
      occurred_on: "2026-03-01",
      text: "",
      payload: { from: "applied", to: "interviews" },
      editable: false,
      created_at: "2026-03-01T15:00:00Z",
    },
  ],
};

describe("ApplicationPage", () => {
  it("shows the card, its decision clock and its timeline", async () => {
    serve({ "GET /api/applications/5": () => json(200, DETAIL) });
    renderPage(<ApplicationPage />, { route: "/applications/:id", path: "/applications/5" });
    expect(await screen.findByRole("heading", { name: "Example Corp" })).toBeInTheDocument();
    expect(screen.getByText(/must say whether a decision has been made by/)).toBeInTheDocument();
    expect(screen.getByText("Moved to Interviews")).toBeInTheDocument();
    expect(screen.getByText("Panel")).toBeInTheDocument();
    // Untrusted text is shown as text, never parsed as markup.
    expect(screen.getByText("<script>not markup</script>")).toBeInTheDocument();
    expect(screen.getByText("<b>Posting text</b> stays text")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Posting/ })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    // Only what the user wrote can be deleted.
    expect(screen.getAllByRole("button", { name: /Delete this/ })).toHaveLength(1);
    expect(screen.getByText("Sam Recruiter")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "sam@example.org" })).toHaveAttribute(
      "href",
      "mailto:sam@example.org",
    );
    expect(screen.getByRole("link", { name: "cv.pdf" })).toHaveAttribute(
      "href",
      "/api/applications/5/documents/31",
    );
  });

  it("uploads a document as a form", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/applications/5": () => json(200, DETAIL),
      "POST /api/applications/5/documents": () => json(201, DETAIL.documents[0]),
    });
    renderPage(<ApplicationPage />, { route: "/applications/:id", path: "/applications/5" });
    const user = userEvent.setup();
    const file = new File(["%PDF-1.7"], "letter.pdf", { type: "application/pdf" });
    await user.upload(await screen.findByLabelText(/File/), file);
    await user.selectOptions(screen.getByLabelText("Kind"), "cover_letter");
    await user.click(screen.getByRole("button", { name: "Upload" }));
    const upload = await vi.waitFor(() => {
      const found = requests.find((request) => request.method === "POST");
      if (!found) throw new Error("not yet");
      return found;
    });
    expect(upload.headers.get("X-CSRFToken")).toBe("token");
    expect(upload.headers.get("Content-Type")).toMatch(/^multipart\/form-data; boundary=/);
    // Read as text: Node's form parser does not accept the test DOM's File objects, and it
    // sends them as an unnamed blob, so only the fields are checked here, not the file name.
    const body = await upload.text();
    expect(body).toMatch(/name="kind"\r\n\r\ncover_letter/);
    expect(body).toContain('name="file"');
  });

  it("adds a contact", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/applications/5": () => json(200, DETAIL),
      "POST /api/applications/5/contacts": () => json(201, DETAIL.contacts[0]),
    });
    renderPage(<ApplicationPage />, { route: "/applications/:id", path: "/applications/5" });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Name"), "Alex Manager");
    await user.type(screen.getByLabelText("Email"), "alex@example.org");
    await user.click(screen.getByRole("button", { name: "Add contact" }));
    const add = await vi.waitFor(() => {
      const found = requests.find((request) => request.method === "POST");
      if (!found) throw new Error("not yet");
      return found;
    });
    expect(await add.json()).toMatchObject({ name: "Alex Manager", email: "alex@example.org" });
  });

  it("adds a note to the timeline", async () => {
    document.cookie = "csrftoken=token";
    const requests = serve({
      "GET /api/applications/5": () => json(200, DETAIL),
      "POST /api/applications/5/events": () => json(201, DETAIL.events[0]),
    });
    renderPage(<ApplicationPage />, { route: "/applications/:id", path: "/applications/5" });
    const user = userEvent.setup();
    await user.type(await screen.findByPlaceholderText("What happened"), "Sent a thank-you");
    await user.clear(screen.getByLabelText("Date"));
    await user.type(screen.getByLabelText("Date"), "2026-03-11");
    await user.click(screen.getByRole("button", { name: "Add to timeline" }));
    const add = requests.find((request) => request.method === "POST");
    expect(await add?.json()).toEqual({
      kind: "note",
      occurred_on: "2026-03-11",
      text: "Sent a thank-you",
    });
  });

  it("is read only for the guest", async () => {
    serve({ "GET /api/applications/5": () => json(200, DETAIL) });
    renderPage(<ApplicationPage />, {
      route: "/applications/:id",
      path: "/applications/5",
      user: GUEST,
    });
    expect(await screen.findByRole("heading", { name: "Example Corp" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add to timeline" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
  });

  it("says when the application does not exist", async () => {
    serve({ "GET /api/applications/5": () => json(404, { detail: "Not Found" }) });
    renderPage(<ApplicationPage />, { route: "/applications/:id", path: "/applications/5" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Not Found");
  });
});
