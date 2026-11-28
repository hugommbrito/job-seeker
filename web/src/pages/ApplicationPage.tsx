import { ArrowLeftIcon, ExternalLinkIcon, Trash2Icon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import {
  type ApplicationDetail,
  type TimelineEvent,
  useAddEvent,
  useApplication,
  useDeleteApplication,
  useDeleteEvent,
  useUpdateApplication,
} from "@/api/applications";
import { ApplicationFields } from "@/components/applications/ApplicationFields";
import { ContactsSection } from "@/components/applications/ContactsSection";
import { DocumentsSection } from "@/components/applications/DocumentsSection";
import { MoveMenu } from "@/components/applications/MoveMenu";
import { StatusBadge } from "@/components/applications/StatusBadge";
import { useCanWrite } from "@/auth/user";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { daysUntil, formatDay, todayIso } from "@/lib/dates";
import { type ApplicationDraft, EMPTY_DRAFT } from "@/lib/draft";
import { isOutcome, isStage, OUTCOME_LABELS, STAGE_LABELS } from "@/lib/stages";

const WAITING_ON_EMPLOYER = new Set(["applied", "recruiter", "interviews"]);

function describe(event: TimelineEvent): string {
  const payload = event.payload as Record<string, string | undefined>;
  switch (event.kind) {
    case "created":
      return `Added${payload.stage && isStage(payload.stage) ? ` as ${STAGE_LABELS[payload.stage]}` : ""}`;
    case "stage_changed":
      return payload.to && isStage(payload.to) ? `Moved to ${STAGE_LABELS[payload.to]}` : "Moved";
    case "closed":
      return payload.outcome && isOutcome(payload.outcome)
        ? `Closed as ${OUTCOME_LABELS[payload.outcome]}`
        : "Closed";
    case "reopened":
      return "Reopened";
    case "interview":
      return "Interview";
    case "note":
      return "Note";
  }
}

function DecisionClock({ application }: { application: ApplicationDetail }) {
  if (!application.last_interview_at || !application.decision_due_at) return null;
  const waiting = application.outcome === null && WAITING_ON_EMPLOYER.has(application.stage);
  const days = daysUntil(application.decision_due_at);
  return (
    <div className="rounded-lg border p-3 text-sm">
      <p>
        Last interview on {formatDay(application.last_interview_at)}. In Ontario, an employer with
        25 or more employees must say whether a decision has been made by{" "}
        <strong>{formatDay(application.decision_due_at)}</strong>.
      </p>
      {waiting && (
        <p className={days < 0 ? "mt-1 text-destructive" : "mt-1 text-muted-foreground"}>
          {days < 0
            ? `${-days} day${days === -1 ? "" : "s"} past that date.`
            : days === 0
              ? "That is today."
              : `${days} day${days === 1 ? "" : "s"} left.`}
        </p>
      )}
    </div>
  );
}

function toDraft(application: ApplicationDetail): ApplicationDraft {
  return {
    ...EMPTY_DRAFT,
    company_name: application.company_name,
    role_title: application.role_title,
    stage: application.stage,
    posting_url: application.posting_url,
    location: application.location,
    source: application.source,
    applied_at: application.applied_at ?? "",
    next_action: application.next_action,
    next_action_due: application.next_action_due ?? "",
    notes: application.notes,
  };
}

function Details({ application }: { application: ApplicationDetail }) {
  const canWrite = useCanWrite();
  const update = useUpdateApplication(application.id);
  const [draft, setDraft] = useState<ApplicationDraft | null>(null);

  function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    update.mutate(
      {
        company_name: draft.company_name,
        role_title: draft.role_title,
        posting_url: draft.posting_url,
        location: draft.location,
        source: draft.source,
        notes: draft.notes,
        applied_at: draft.applied_at || null,
        next_action: draft.next_action,
        next_action_due: draft.next_action_due || null,
      },
      { onSuccess: () => setDraft(null) },
    );
  }

  if (draft) {
    return (
      <form onSubmit={save} className="flex flex-col gap-4">
        <ApplicationFields value={draft} onChange={setDraft} pastFields={false} stageField={false} />
        {update.isError && (
          <p role="alert" className="text-sm text-destructive">
            {update.error.message}
          </p>
        )}
        <div className="flex gap-2">
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save"}
          </Button>
          <Button type="button" variant="outline" onClick={() => setDraft(null)}>
            Cancel
          </Button>
        </div>
      </form>
    );
  }

  const rows: [string, React.ReactNode][] = [
    ["Location", application.location],
    ["Found through", application.source],
    ["Applied on", formatDay(application.applied_at)],
    [
      "Next action",
      application.next_action || application.next_action_due
        ? `${application.next_action}${application.next_action_due ? ` (by ${formatDay(application.next_action_due)})` : ""}`
        : "",
    ],
  ];

  return (
    <div className="flex flex-col gap-3 text-sm">
      {application.posting_url && (
        <a
          href={application.posting_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 break-all underline underline-offset-4"
        >
          Posting <ExternalLinkIcon className="size-3.5" />
        </a>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        {rows
          .filter(([, value]) => value)
          .map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
      </dl>
      {application.notes && <p className="whitespace-pre-wrap">{application.notes}</p>}
      {canWrite && (
        <div>
          <Button variant="outline" size="sm" onClick={() => setDraft(toDraft(application))}>
            Edit details
          </Button>
        </div>
      )}
    </div>
  );
}

function AddToTimeline({ applicationId }: { applicationId: number }) {
  const add = useAddEvent(applicationId);
  const [kind, setKind] = useState<"note" | "interview">("note");
  const [day, setDay] = useState(todayIso());
  const [text, setText] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    add.mutate(
      { kind, occurred_on: day || null, text },
      {
        onSuccess: () => {
          setText("");
          setDay(todayIso());
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex flex-wrap gap-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor="event-kind" className="text-xs">
            Add
          </Label>
          <NativeSelect
            id="event-kind"
            value={kind}
            onChange={(event) => setKind(event.target.value === "interview" ? "interview" : "note")}
          >
            <NativeSelectOption value="note">Note</NativeSelectOption>
            <NativeSelectOption value="interview">Interview</NativeSelectOption>
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="event-day" className="text-xs">
            Date
          </Label>
          <Input
            id="event-day"
            type="date"
            required
            value={day}
            onChange={(event) => setDay(event.target.value)}
          />
        </div>
      </div>
      <Label htmlFor="event-text" className="sr-only">
        Details
      </Label>
      <Textarea
        id="event-text"
        rows={2}
        maxLength={5000}
        placeholder={kind === "interview" ? "Who, what kind of interview…" : "What happened"}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      {add.isError && (
        <p role="alert" className="text-sm text-destructive">
          {add.error.message}
        </p>
      )}
      <div>
        <Button type="submit" size="sm" disabled={add.isPending}>
          Add to timeline
        </Button>
      </div>
    </form>
  );
}

function Timeline({ application }: { application: ApplicationDetail }) {
  const canWrite = useCanWrite();
  const remove = useDeleteEvent(application.id);
  return (
    <div className="flex flex-col gap-3">
      {canWrite && <AddToTimeline applicationId={application.id} />}
      <ol className="flex flex-col gap-3 border-l pl-4">
        {application.events.map((event) => (
          <li key={event.id} className="flex flex-col gap-0.5 text-sm">
            <span className="flex items-center gap-2">
              <span className="font-medium">{describe(event)}</span>
              <span className="text-muted-foreground">{formatDay(event.occurred_on)}</span>
              {canWrite && event.editable && (
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Delete this ${event.kind}`}
                  onClick={() => remove.mutate(event.id)}
                >
                  <Trash2Icon />
                </Button>
              )}
            </span>
            {event.text && <p className="whitespace-pre-wrap">{event.text}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function PostingSnapshot({ application }: { application: ApplicationDetail }) {
  const snapshot = application.posting_snapshot as Record<string, unknown>;
  const description = typeof snapshot.description === "string" ? snapshot.description : "";
  if (!description) return null;
  return (
    <details className="rounded-lg border p-3 text-sm">
      <summary className="cursor-pointer font-medium">The posting, as it was saved</summary>
      {/* Posting text is untrusted: it is rendered as text, never as markup. */}
      <p className="mt-2 whitespace-pre-wrap">{description}</p>
    </details>
  );
}

function DeleteButton({ application }: { application: ApplicationDetail }) {
  const remove = useDeleteApplication();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setConfirming(true)}>
        <Trash2Icon /> Delete
      </Button>
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this application?</DialogTitle>
            <DialogDescription>
              {application.company_name}, {application.role_title}, and its whole timeline. This
              cannot be undone. To keep it but take it off the board, close it instead.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(application.id, { onSuccess: () => void navigate("/board") })
              }
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function ApplicationPage() {
  const params = useParams();
  const id = Number(params.id);
  const application = useApplication(id);
  const canWrite = useCanWrite();

  if (application.isPending) {
    return <p className="p-4 text-sm text-muted-foreground">Loading…</p>;
  }
  if (application.isError) {
    return (
      <div className="flex flex-col gap-2 p-4">
        <p role="alert" className="text-sm">
          {application.error.message}
        </p>
        <Link to="/board" className="text-sm underline">
          Back to the board
        </Link>
      </div>
    );
  }

  const data = application.data;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4">
      <Link to="/board" className="inline-flex items-center gap-1 text-sm text-muted-foreground">
        <ArrowLeftIcon className="size-4" /> Board
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="font-heading text-xl font-semibold break-words">{data.company_name}</h1>
          <p className="text-muted-foreground break-words">{data.role_title}</p>
          <StatusBadge stage={data.stage} outcome={data.outcome} />
        </div>
        {canWrite && (
          <div className="flex items-center gap-1">
            <MoveMenu application={data} />
            <DeleteButton application={data} />
          </div>
        )}
      </div>
      <DecisionClock application={data} />
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent>
          <Details application={data} />
        </CardContent>
      </Card>
      <PostingSnapshot application={data} />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Contacts</CardTitle>
          </CardHeader>
          <CardContent>
            <ContactsSection application={data} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Documents sent</CardTitle>
          </CardHeader>
          <CardContent>
            <DocumentsSection application={data} />
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <Timeline application={data} />
        </CardContent>
      </Card>
    </div>
  );
}
