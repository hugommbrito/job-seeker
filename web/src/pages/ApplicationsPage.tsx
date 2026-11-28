import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";

import { useApplications } from "@/api/applications";
import { ImportDialog } from "@/components/applications/ImportDialog";
import { NewApplicationDialog } from "@/components/applications/NewApplicationDialog";
import { StatusBadge } from "@/components/applications/StatusBadge";
import { useCanWrite } from "@/auth/user";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDay, formatInstant } from "@/lib/dates";
import {
  activeFilterCount,
  DEFAULT_FILTERS,
  type SortKey,
  type StatusFilter,
  useFilters,
} from "@/lib/filters";
import { STAGE_LABELS, STAGES } from "@/lib/stages";

const SORT_LABELS: Record<SortKey, string> = {
  updated: "Recently updated",
  company: "Company",
  applied: "Applied date",
  next_action: "Next action due",
};

const STATUS_LABELS: Record<StatusFilter, string> = {
  all: "All",
  open: "Open",
  closed: "Closed",
};

/** A search box that writes to the URL after the typing stops, not on every key. */
function SearchBox({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [text, setText] = useState(value);
  // When the URL changes from elsewhere (back button, "Clear filters"), show what it says.
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    setShown(value);
    setText(value);
  }
  useEffect(() => {
    if (text === value) return;
    const timer = setTimeout(() => onChange(text), 300);
    return () => clearTimeout(timer);
  }, [text, value, onChange]);
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor="filter-q" className="text-xs">
        Search
      </Label>
      <Input
        id="filter-q"
        type="search"
        placeholder="Company or role"
        className="w-56"
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
    </div>
  );
}

export function ApplicationsPage() {
  const [filters, setFilters] = useFilters();
  const applications = useApplications(filters);
  const canWrite = useCanWrite();
  const navigate = useNavigate();
  const rows = applications.data ?? [];

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="font-heading text-lg font-semibold">Applications</h1>
        {canWrite && (
          <div className="flex gap-2">
            <ImportDialog />
            <NewApplicationDialog />
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <SearchBox value={filters.q} onChange={(q) => setFilters({ q })} />
        <div className="flex flex-col gap-1">
          <Label htmlFor="filter-status" className="text-xs">
            Status
          </Label>
          <NativeSelect
            id="filter-status"
            value={filters.status}
            onChange={(event) => setFilters({ status: event.target.value as StatusFilter })}
          >
            {(Object.keys(STATUS_LABELS) as StatusFilter[]).map((status) => (
              <NativeSelectOption key={status} value={status}>
                {STATUS_LABELS[status]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium">Stages</span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-8">
                {filters.stages.length === 0
                  ? "Any stage"
                  : filters.stages.map((stage) => STAGE_LABELS[stage]).join(", ")}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-48">
              <DropdownMenuLabel>Show stages</DropdownMenuLabel>
              {STAGES.map((stage) => {
                const id = `filter-stage-${stage}`;
                const checked = filters.stages.includes(stage);
                return (
                  <div key={stage} className="flex items-center gap-2 px-2 py-1.5 text-sm">
                    <Checkbox
                      id={id}
                      checked={checked}
                      onCheckedChange={(next) =>
                        setFilters({
                          stages: next
                            ? STAGES.filter((s) => s === stage || filters.stages.includes(s))
                            : filters.stages.filter((s) => s !== stage),
                        })
                      }
                    />
                    <Label htmlFor={id} className="font-normal">
                      {STAGE_LABELS[stage]}
                    </Label>
                  </div>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="filter-sort" className="text-xs">
            Sort by
          </Label>
          <NativeSelect
            id="filter-sort"
            value={filters.sort}
            onChange={(event) => setFilters({ sort: event.target.value as SortKey })}
          >
            {(Object.keys(SORT_LABELS) as SortKey[]).map((sort) => (
              <NativeSelectOption key={sort} value={sort}>
                {SORT_LABELS[sort]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        {activeFilterCount(filters) > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setFilters(DEFAULT_FILTERS)}>
            Clear filters
          </Button>
        )}
      </div>

      {applications.isError && (
        <p role="alert" className="text-sm text-destructive">
          {applications.error.message}
        </p>
      )}
      {applications.isSuccess && rows.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {activeFilterCount(filters) > 0
            ? "No application matches these filters."
            : "No applications yet."}
        </p>
      )}
      {rows.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Applied</TableHead>
              <TableHead>Next action</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow
                key={row.id}
                className="cursor-pointer"
                onClick={() => void navigate(`/applications/${row.id}`)}
              >
                <TableCell className="font-medium">
                  <Link to={`/applications/${row.id}`} onClick={(e) => e.stopPropagation()}>
                    {row.company_name}
                  </Link>
                </TableCell>
                <TableCell className="max-w-64 truncate">{row.role_title}</TableCell>
                <TableCell>
                  <StatusBadge stage={row.stage} outcome={row.outcome} />
                </TableCell>
                <TableCell>{formatDay(row.applied_at)}</TableCell>
                <TableCell className="max-w-56 truncate">
                  {row.next_action}
                  {row.next_action_due && (
                    <span className="text-muted-foreground"> · {formatDay(row.next_action_due)}</span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatInstant(row.updated_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
