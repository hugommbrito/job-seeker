import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS, filtersFromQuery, queryFromFilters } from "@/lib/filters";

describe("filters in the URL", () => {
  it("keeps only what differs from the defaults", () => {
    expect(queryFromFilters(DEFAULT_FILTERS).toString()).toBe("");
    expect(
      queryFromFilters({ status: "open", stages: ["applied", "offer"], q: " x ", sort: "company" })
        .toString(),
    ).toBe("status=open&stage=applied%2Coffer&q=x&sort=company");
  });

  it("round-trips, and ignores what it does not recognise", () => {
    const filters = filtersFromQuery(new URLSearchParams("status=closed&stage=offer,bogus&sort=nope"));
    expect(filters).toEqual({ status: "closed", stages: ["offer"], q: "", sort: "updated" });
    expect(filtersFromQuery(queryFromFilters(filters))).toEqual(filters);
  });
});
