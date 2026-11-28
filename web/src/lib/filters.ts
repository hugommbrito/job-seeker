import { useCallback } from "react";
import { useSearchParams } from "react-router";

import { isStage, type Stage } from "@/lib/stages";

export type StatusFilter = "open" | "closed" | "all";
export type SortKey = "updated" | "company" | "applied" | "next_action";

export interface Filters {
  status: StatusFilter;
  stages: Stage[];
  q: string;
  sort: SortKey;
}

export const DEFAULT_FILTERS: Filters = { status: "all", stages: [], q: "", sort: "updated" };

const STATUSES: readonly StatusFilter[] = ["open", "closed", "all"];
export const SORTS: readonly SortKey[] = ["updated", "company", "applied", "next_action"];

export function filtersFromQuery(query: URLSearchParams): Filters {
  const status = query.get("status") ?? "";
  const sort = query.get("sort") ?? "";
  return {
    status: (STATUSES as readonly string[]).includes(status)
      ? (status as StatusFilter)
      : DEFAULT_FILTERS.status,
    stages: (query.get("stage") ?? "").split(",").filter(isStage),
    q: query.get("q") ?? "",
    sort: (SORTS as readonly string[]).includes(sort) ? (sort as SortKey) : DEFAULT_FILTERS.sort,
  };
}

/** Only what differs from the defaults, so the plain list is a plain URL. */
export function queryFromFilters(filters: Filters): URLSearchParams {
  const query = new URLSearchParams();
  if (filters.status !== DEFAULT_FILTERS.status) query.set("status", filters.status);
  if (filters.stages.length > 0) query.set("stage", filters.stages.join(","));
  if (filters.q.trim()) query.set("q", filters.q.trim());
  if (filters.sort !== DEFAULT_FILTERS.sort) query.set("sort", filters.sort);
  return query;
}

export function activeFilterCount(filters: Filters): number {
  return [
    filters.status !== DEFAULT_FILTERS.status,
    filters.stages.length > 0,
    filters.q.trim() !== "",
  ].filter(Boolean).length;
}

/** Filters live in the URL, so a filtered view can be bookmarked, shared and reloaded. */
export function useFilters(): [Filters, (patch: Partial<Filters>) => void] {
  const [query, setQuery] = useSearchParams();
  const filters = filtersFromQuery(query);
  const update = useCallback(
    (patch: Partial<Filters>) => {
      setQuery(queryFromFilters({ ...filtersFromQuery(query), ...patch }), { replace: true });
    },
    [query, setQuery],
  );
  return [filters, update];
}
