import { type FormEvent, type ReactNode, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import {
  type Capture,
  type CaptureSave,
  type Proposal,
  useCapture,
  useDiscardCapture,
  useReadAgain,
  useSaveCapture,
} from "@/api/captures";
import { useCanWrite } from "@/auth/user";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { isStage, STAGE_LABELS, STAGES } from "@/lib/stages";

/** The review form: every field as text, so an empty input is "" and never undefined. */
interface Review {
  title: string;
  company_name: string;
  location_text: string;
  workplace_type: string;
  employment_type: string;
  salary_min: string;
  salary_max: string;
  salary_currency: string;
  salary_period: string;
  application_deadline: string;
  ai_screening: string;
  existing_vacancy: string;
  posting_url: string;
  stage: string;
  applied_at: string;
  next_action: string;
  next_action_due: string;
}

function reviewFrom(capture: Capture): Review {
  const p: Partial<Proposal> = capture.proposal ?? {};
  const amount = (value: number | null | undefined) => (value == null ? "" : String(value));
  return {
    title: p.title ?? "",
    company_name: p.company ?? "",
    location_text: p.location ?? "",
    workplace_type: p.workplace_type ?? "unknown",
    employment_type: p.employment_type ?? "unknown",
    salary_min: amount(p.salary_min),
    salary_max: amount(p.salary_max),
    salary_currency: p.salary_currency ?? "",
    salary_period: p.salary_period ?? "unknown",
    application_deadline: p.application_deadline ?? "",
    ai_screening: p.ai_screening ?? "unknown",
    existing_vacancy: p.existing_vacancy ?? "unknown",
    posting_url: capture.url,
    stage: "saved",
    applied_at: "",
    next_action: "",
    next_action_due: "",
  };
}

function toBody(review: Review): CaptureSave {
  const orNull = (value: string) => (value ? value : null);
  return {
    title: review.title,
    company_name: review.company_name,
    location_text: review.location_text,
    workplace_type: review.workplace_type as CaptureSave["workplace_type"],
    employment_type: review.employment_type as CaptureSave["employment_type"],
    salary_min: orNull(review.salary_min),
    salary_max: orNull(review.salary_max),
    salary_currency: review.salary_currency,
    salary_period: review.salary_period as CaptureSave["salary_period"],
    application_deadline: orNull(review.application_deadline),
    ai_screening: review.ai_screening as CaptureSave["ai_screening"],
    existing_vacancy: review.existing_vacancy as CaptureSave["existing_vacancy"],
    posting_url: review.posting_url,
    stage: isStage(review.stage) ? review.stage : "saved",
    applied_at: orNull(review.applied_at),
    next_action: review.next_action,
    next_action_due: orNull(review.next_action_due),
    notes: "",
  };
}

const REASONS: Record<string, string> = {
  unavailable: "no model is configured on this server",
  refused: "the model declined to read it",
  truncated: "the model's answer was cut off",
  invalid: "the model's answer was not usable",
  error: "the model could not be reached",
  over_budget: "today's limit of model calls has been reached",
  denied: "this account cannot use the model",
  stalled: "it was never picked up by the background worker",
};

function Hint({ quote, flagged }: { quote?: string; flagged?: boolean }) {
  if (flagged) {
    return (
      <p className="text-xs text-destructive">
        The value read here was not found in the posting, so it was left out. Check the text.
      </p>
    );
  }
  if (!quote) return null;
  // The quote is untrusted posting text: shown as text, never as markup.
  return <p className="text-xs text-muted-foreground">From the posting: “{quote}”</p>;
}

function Field({
  id,
  label,
  children,
  quote,
  flagged,
  wide,
}: {
  id: string;
  label: string;
  children: ReactNode;
  quote?: string;
  flagged?: boolean;
  wide?: boolean;
}) {
  return (
    <div className={wide ? "flex flex-col gap-1 sm:col-span-2" : "flex flex-col gap-1"}>
      <Label htmlFor={id}>{label}</Label>
      {children}
      <Hint quote={quote} flagged={flagged} />
    </div>
  );
}

function Choice({
  id,
  value,
  onChange,
  options,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  return (
    <NativeSelect
      id={id}
      className="w-full"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      {options.map(([option, label]) => (
        <NativeSelectOption key={option} value={option}>
          {label}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  );
}

const TRI: [string, string][] = [
  ["unknown", "Not stated"],
  ["yes", "Yes"],
  ["no", "No"],
];

function ReviewForm({ capture, initial }: { capture: Capture; initial: Review }) {
  const [review, setReview] = useState(initial);
  const save = useSaveCapture(capture.id);
  const navigate = useNavigate();
  const proposal = capture.proposal;
  const issues = new Set(proposal?.issues ?? []);

  function set(name: keyof Review) {
    return (value: string) => setReview({ ...review, [name]: value });
  }
  function input(name: keyof Review) {
    return {
      id: `review-${name}`,
      value: review[name],
      onChange: (event: { target: { value: string } }) => set(name)(event.target.value),
    };
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(toBody(review), {
      onSuccess: (application) => void navigate(`/applications/${application.id}`),
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="review-title" label="Role" quote={proposal?.title_quote} flagged={issues.has("title")}>
          <Input required maxLength={300} {...input("title")} />
        </Field>
        <Field
          id="review-company_name"
          label="Company"
          quote={proposal?.company_quote}
          flagged={issues.has("company")}
        >
          <Input required maxLength={200} {...input("company_name")} />
        </Field>
        <Field
          id="review-location_text"
          label="Location"
          quote={proposal?.location_quote}
          flagged={issues.has("location")}
        >
          <Input maxLength={200} {...input("location_text")} />
        </Field>
        <Field
          id="review-workplace_type"
          label="Workplace"
          quote={proposal?.workplace_quote}
          flagged={issues.has("workplace_type")}
        >
          <Choice
            id="review-workplace_type"
            value={review.workplace_type}
            onChange={set("workplace_type")}
            options={[
              ["unknown", "Not stated"],
              ["remote", "Remote"],
              ["hybrid", "Hybrid"],
              ["onsite", "On site"],
            ]}
          />
        </Field>
        <Field
          id="review-employment_type"
          label="Employment"
          quote={proposal?.employment_quote}
          flagged={issues.has("employment_type")}
        >
          <Choice
            id="review-employment_type"
            value={review.employment_type}
            onChange={set("employment_type")}
            options={[
              ["unknown", "Not stated"],
              ["full_time", "Full time"],
              ["part_time", "Part time"],
              ["contract", "Contract"],
              ["temporary", "Temporary"],
              ["internship", "Internship"],
            ]}
          />
        </Field>
        <Field
          id="review-application_deadline"
          label="Applications close"
          quote={proposal?.deadline_quote}
          flagged={issues.has("application_deadline")}
        >
          <Input type="date" {...input("application_deadline")} />
        </Field>
        <fieldset className="grid gap-3 rounded-lg border p-3 sm:col-span-2 sm:grid-cols-4">
          <legend className="px-1 text-xs text-muted-foreground">Salary</legend>
          <Field id="review-salary_min" label="From">
            <Input inputMode="decimal" {...input("salary_min")} />
          </Field>
          <Field id="review-salary_max" label="To">
            <Input inputMode="decimal" {...input("salary_max")} />
          </Field>
          <Field id="review-salary_currency" label="Currency">
            <Input maxLength={3} placeholder="CAD" {...input("salary_currency")} />
          </Field>
          <Field id="review-salary_period" label="Per">
            <Choice
              id="review-salary_period"
              value={review.salary_period}
              onChange={set("salary_period")}
              options={[
                ["unknown", "Not stated"],
                ["year", "Year"],
                ["month", "Month"],
                ["week", "Week"],
                ["day", "Day"],
                ["hour", "Hour"],
              ]}
            />
          </Field>
          <div className="sm:col-span-4">
            <Hint quote={proposal?.salary_quote} flagged={issues.has("salary")} />
          </div>
        </fieldset>
        <Field
          id="review-ai_screening"
          label="Says AI screens applicants"
          quote={proposal?.ai_screening_quote}
          flagged={issues.has("ai_screening")}
        >
          <Choice id="review-ai_screening" value={review.ai_screening} onChange={set("ai_screening")} options={TRI} />
        </Field>
        <Field
          id="review-existing_vacancy"
          label="Says it is an existing vacancy"
          quote={proposal?.existing_vacancy_quote}
          flagged={issues.has("existing_vacancy")}
        >
          <Choice
            id="review-existing_vacancy"
            value={review.existing_vacancy}
            onChange={set("existing_vacancy")}
            options={TRI}
          />
        </Field>
        <Field id="review-posting_url" label="Posting URL" wide>
          <Input type="url" placeholder="https://" {...input("posting_url")} />
        </Field>
      </div>

      <fieldset className="grid gap-4 rounded-lg border p-3 sm:grid-cols-2">
        <legend className="px-1 text-xs text-muted-foreground">The application</legend>
        <Field id="review-stage" label="Stage">
          <Choice
            id="review-stage"
            value={review.stage}
            onChange={set("stage")}
            options={STAGES.map((stage) => [stage, STAGE_LABELS[stage]])}
          />
        </Field>
        <Field id="review-applied_at" label="Applied on">
          <Input type="date" {...input("applied_at")} />
        </Field>
        <Field id="review-next_action" label="Next action">
          <Input maxLength={300} {...input("next_action")} />
        </Field>
        <Field id="review-next_action_due" label="Next action due">
          <Input type="date" {...input("next_action_due")} />
        </Field>
      </fieldset>

      {save.isError && (
        <p role="alert" className="text-sm text-destructive">
          {save.error.message}
        </p>
      )}
      <div>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save as an application"}
        </Button>
      </div>
    </form>
  );
}

export function ReviewCapturePage() {
  const id = Number(useParams().id);
  const capture = useCapture(id);
  const readAgain = useReadAgain(id);
  const discard = useDiscardCapture();
  const canWrite = useCanWrite();
  const navigate = useNavigate();
  const [byHand, setByHand] = useState(false);

  if (capture.isPending) return <p className="p-4 text-sm text-muted-foreground">Loading…</p>;
  if (capture.isError) {
    return (
      <p role="alert" className="p-4 text-sm">
        {capture.error.message}
      </p>
    );
  }

  const data = capture.data;
  const reading = data.extraction_status === "pending" && !byHand;

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 p-4">
      <Link to="/capture" className="text-sm text-muted-foreground">
        ← Add a posting
      </Link>
      <h1 className="font-heading text-lg font-semibold">Review the posting</h1>

      {data.application_id !== null && (
        <p className="text-sm">
          Already saved.{" "}
          <Link to={`/applications/${data.application_id}`} className="underline">
            Open the application
          </Link>
        </p>
      )}

      {reading && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm">
          <span>Reading the posting…</span>
          {canWrite && (
            <Button variant="outline" size="sm" onClick={() => setByHand(true)}>
              Fill in by hand instead
            </Button>
          )}
        </div>
      )}
      {data.extraction_status === "not_evaluated" && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm">
          <span>
            The posting was not read automatically
            {data.extraction_error && REASONS[data.extraction_error]
              ? `: ${REASONS[data.extraction_error]}`
              : ""}
            . Fill in the fields below.
          </span>
          {canWrite && (
            <Button
              variant="outline"
              size="sm"
              disabled={readAgain.isPending}
              onClick={() => readAgain.mutate()}
            >
              Try reading it again
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
        <Card>
          <CardHeader>
            <CardTitle>Fields</CardTitle>
          </CardHeader>
          <CardContent>
            {reading ? (
              <p className="text-sm text-muted-foreground">
                The fields appear here once the posting has been read.
              </p>
            ) : canWrite && data.application_id === null ? (
              // Keyed by status so the form starts over from the proposal when a reading lands.
              <ReviewForm
                key={`${data.extraction_status}-${byHand}`}
                capture={data}
                initial={reviewFrom(data)}
              />
            ) : (
              <p className="text-sm text-muted-foreground">Nothing to review.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>The posting</CardTitle>
          </CardHeader>
          <CardContent>
            {/* Untrusted text: rendered as text, never as markup. */}
            <p className="max-h-[70svh] overflow-y-auto text-sm whitespace-pre-wrap">
              {data.description_text}
            </p>
          </CardContent>
        </Card>
      </div>

      {canWrite && data.application_id === null && (
        <div>
          <Button
            variant="ghost"
            size="sm"
            disabled={discard.isPending}
            onClick={() => discard.mutate(data.id, { onSuccess: () => void navigate("/capture") })}
          >
            Discard this posting
          </Button>
        </div>
      )}
    </div>
  );
}
