import type { ApplicationInput } from "@/api/applications";
import { isOutcome, isStage } from "@/lib/stages";

/** What the form holds: every field as text, so an empty input is "" and never undefined. */
export interface ApplicationDraft {
  company_name: string;
  role_title: string;
  stage: string;
  posting_url: string;
  location: string;
  source: string;
  applied_at: string;
  next_action: string;
  next_action_due: string;
  notes: string;
  outcome: string;
  last_interview_at: string;
  closed_on: string;
}

export const EMPTY_DRAFT: ApplicationDraft = {
  company_name: "",
  role_title: "",
  stage: "saved",
  posting_url: "",
  location: "",
  source: "",
  applied_at: "",
  next_action: "",
  next_action_due: "",
  notes: "",
  outcome: "",
  last_interview_at: "",
  closed_on: "",
};

/** The request body for a draft: empty dates are left out instead of sent as "". */
export function draftToInput(draft: ApplicationDraft): ApplicationInput {
  const date = (value: string) => (value ? value : null);
  return {
    company_name: draft.company_name,
    role_title: draft.role_title,
    stage: isStage(draft.stage) ? draft.stage : "saved",
    outcome: isOutcome(draft.outcome) ? draft.outcome : null,
    posting_url: draft.posting_url,
    location: draft.location,
    source: draft.source,
    notes: draft.notes,
    applied_at: date(draft.applied_at),
    next_action: draft.next_action,
    next_action_due: date(draft.next_action_due),
    last_interview_at: date(draft.last_interview_at),
    closed_on: isOutcome(draft.outcome) ? date(draft.closed_on) : null,
  };
}
