/**
 * The API sends calendar dates as "YYYY-MM-DD". They name a day, not an instant, so they are
 * read as local dates: `new Date("2026-03-02")` would be UTC midnight and show the day before
 * anywhere west of Greenwich.
 */
export function parseDay(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year ?? 1970, (month ?? 1) - 1, day ?? 1);
}

const DAY_FORMAT = new Intl.DateTimeFormat("en-CA", { dateStyle: "medium" });
const DATE_TIME_FORMAT = new Intl.DateTimeFormat("en-CA", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatDay(value: string | null | undefined): string {
  return value ? DAY_FORMAT.format(parseDay(value)) : "";
}

export function formatInstant(value: string | null | undefined): string {
  return value ? DATE_TIME_FORMAT.format(new Date(value)) : "";
}

export function todayIso(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/** Whole days from today to `value`: negative when it is in the past. */
export function daysUntil(value: string, now: Date = new Date()): number {
  const today = parseDay(todayIso(now));
  return Math.round((parseDay(value).getTime() - today.getTime()) / 86_400_000);
}
