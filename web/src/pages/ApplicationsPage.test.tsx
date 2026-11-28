import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ApplicationsPage } from "@/pages/ApplicationsPage";
import { application, renderPage } from "@/test/render";
import { json, serve } from "@/test/server";

function queryOf(request: Request) {
  return new URL(request.url).searchParams;
}

describe("ApplicationsPage", () => {
  it("reads its filters from the URL and sends them to the API", async () => {
    const requests = serve({
      "GET /api/applications": () => json(200, [application({ company_name: "Alpha" })]),
    });
    renderPage(<ApplicationsPage />, {
      route: "/applications",
      path: "/applications?status=open&stage=applied,interviews&q=alp&sort=company",
    });
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    const query = queryOf(requests[0]!);
    expect(query.get("status")).toBe("open");
    expect(query.getAll("stage")).toEqual(["applied", "interviews"]);
    expect(query.get("q")).toBe("alp");
    expect(query.get("sort")).toBe("company");
    expect(screen.getByLabelText("Status")).toHaveValue("open");
  });

  it("writes a changed filter to the URL and asks again", async () => {
    const requests = serve({ "GET /api/applications": () => json(200, []) });
    renderPage(<ApplicationsPage />, { route: "/applications", path: "/applications" });
    const user = userEvent.setup();
    await screen.findByText("No applications yet.");
    await user.selectOptions(screen.getByLabelText("Status"), "closed");
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("/applications?status=closed"),
    );
    await waitFor(() => expect(queryOf(requests.at(-1)!).get("status")).toBe("closed"));
    expect(await screen.findByText("No application matches these filters.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(/^\/applications$/));
  });

  it("opens an application from its row", async () => {
    serve({ "GET /api/applications": () => json(200, [application({ id: 4 })]) });
    renderPage(<ApplicationsPage />, { route: "/applications", path: "/applications" });
    const user = userEvent.setup();
    await user.click(await screen.findByText("Software Engineer"));
    expect(screen.getByTestId("location")).toHaveTextContent("/applications/4");
  });
});
