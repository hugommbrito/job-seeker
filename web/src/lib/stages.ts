import type { components } from "@/api/schema";

export type Stage = components["schemas"]["Stage"];
export type Outcome = components["schemas"]["Outcome"];

/** Board order. A card moves left to right as the application progresses. */
export const STAGES: readonly Stage[] = [
  "discovered",
  "saved",
  "preparing",
  "applied",
  "recruiter",
  "interviews",
  "offer",
  "accepted",
];

export const OUTCOMES: readonly Outcome[] = ["rejected", "ghosted", "withdrawn"];

export const STAGE_LABELS: Record<Stage, string> = {
  discovered: "Discovered",
  saved: "Saved",
  preparing: "Preparing",
  applied: "Applied",
  recruiter: "Recruiter",
  interviews: "Interviews",
  offer: "Offer",
  accepted: "Accepted",
};

export const OUTCOME_LABELS: Record<Outcome, string> = {
  rejected: "Rejected",
  ghosted: "Ghosted",
  withdrawn: "Withdrawn",
};

export function isStage(value: string): value is Stage {
  return (STAGES as readonly string[]).includes(value);
}

export function isOutcome(value: string): value is Outcome {
  return (OUTCOMES as readonly string[]).includes(value);
}
