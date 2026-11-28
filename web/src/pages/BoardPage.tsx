import {
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useState } from "react";
import { Link } from "react-router";

import { type Application, useApplications, useTransition } from "@/api/applications";
import { MoveMenu } from "@/components/applications/MoveMenu";
import { NewApplicationDialog } from "@/components/applications/NewApplicationDialog";
import { useCanWrite } from "@/auth/user";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { daysUntil, formatDay } from "@/lib/dates";
import {
  isStage,
  OUTCOME_LABELS,
  OUTCOMES,
  type Outcome,
  STAGE_LABELS,
  STAGES,
  type Stage,
} from "@/lib/stages";
import { cn } from "@/lib/utils";

const CLOSED = "closed";
const WAITING_ON_EMPLOYER: readonly Stage[] = ["applied", "recruiter", "interviews"];

function DueBadge({ application }: { application: Application }) {
  if (application.outcome !== null) return null;
  if (application.next_action_due) {
    const days = daysUntil(application.next_action_due);
    return (
      <Badge variant={days < 0 ? "destructive" : "outline"}>
        {days < 0 ? "Overdue" : days === 0 ? "Due today" : `Due ${formatDay(application.next_action_due)}`}
      </Badge>
    );
  }
  if (application.decision_due_at && WAITING_ON_EMPLOYER.includes(application.stage)) {
    const days = daysUntil(application.decision_due_at);
    return (
      <Badge variant={days < 0 ? "destructive" : "outline"}>
        {days < 0 ? "Decision overdue" : `Decision by ${formatDay(application.decision_due_at)}`}
      </Badge>
    );
  }
  return null;
}

function Card({ application, draggable }: { application: Application; draggable: boolean }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: application.id,
    disabled: !draggable,
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  return (
    <li
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      aria-roledescription={draggable ? "draggable application" : undefined}
      className={cn(
        "flex items-start gap-1 rounded-lg border bg-card p-2 text-sm shadow-xs",
        isDragging && "relative z-10 opacity-80 shadow-md",
        draggable && "cursor-grab active:cursor-grabbing",
      )}
    >
      <Link
        to={`/applications/${application.id}`}
        className="flex min-w-0 flex-1 flex-col gap-1 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="truncate font-medium">{application.company_name}</span>
        <span className="line-clamp-2 text-muted-foreground">{application.role_title}</span>
        {application.next_action && application.outcome === null && (
          <span className="line-clamp-1 text-xs">{application.next_action}</span>
        )}
        <span className="flex flex-wrap gap-1">
          {application.outcome && (
            <Badge variant="destructive">{OUTCOME_LABELS[application.outcome]}</Badge>
          )}
          <DueBadge application={application} />
        </span>
      </Link>
      {draggable && <MoveMenu application={application} />}
    </li>
  );
}

function Column({
  id,
  title,
  applications,
  draggable,
}: {
  id: string;
  title: string;
  applications: Application[];
  draggable: boolean;
}) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <section
      ref={setNodeRef}
      aria-label={title}
      className={cn(
        "flex w-64 shrink-0 flex-col gap-2 rounded-xl bg-muted/60 p-2 transition-colors",
        isOver && "bg-muted ring-2 ring-ring/40",
      )}
    >
      <h2 className="flex items-center justify-between px-1 text-sm font-medium">
        {title}
        <span className="text-xs text-muted-foreground">{applications.length}</span>
      </h2>
      <ul className="flex min-h-16 flex-col gap-2">
        {applications.map((application) => (
          <Card key={application.id} application={application} draggable={draggable} />
        ))}
      </ul>
    </section>
  );
}

function OutcomeDialog({
  application,
  onPick,
  onCancel,
}: {
  application: Application | null;
  onPick: (outcome: Outcome) => void;
  onCancel: () => void;
}) {
  return (
    <Dialog open={application !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>How did it end?</DialogTitle>
          <DialogDescription>
            {application?.company_name}, {application?.role_title}. The stage it reached is kept.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap gap-2">
          {OUTCOMES.map((outcome) => (
            <Button key={outcome} variant="outline" onClick={() => onPick(outcome)}>
              {OUTCOME_LABELS[outcome]}
            </Button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function BoardPage() {
  const applications = useApplications();
  const move = useTransition();
  const canWrite = useCanWrite();
  const [closing, setClosing] = useState<Application | null>(null);
  const sensors = useSensors(
    // A short travel before a drag starts, so a tap on a card still opens it.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );

  const rows = applications.data ?? [];
  const open = rows.filter((row) => row.outcome === null);
  const closed = rows.filter((row) => row.outcome !== null);

  async function onDragEnd(event: DragEndEvent) {
    const target = event.over ? String(event.over.id) : null;
    const application = rows.find((row) => row.id === event.active.id);
    if (!target || !application) return;
    if (target === CLOSED) {
      if (application.outcome === null) setClosing(application);
      return;
    }
    if (!isStage(target)) return;
    if (application.outcome !== null) {
      await move.mutateAsync({ id: application.id, reopen: true });
    } else if (application.stage === target) {
      return;
    }
    move.mutate({ id: application.id, stage: target });
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="font-heading text-lg font-semibold">Board</h1>
        {canWrite && <NewApplicationDialog />}
      </div>
      {applications.isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
      {applications.isError && (
        <p role="alert" className="text-sm text-destructive">
          {applications.error.message}
        </p>
      )}
      {move.isError && (
        <p role="alert" className="text-sm text-destructive">
          {move.error.message}
        </p>
      )}
      {applications.isSuccess && rows.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-16 text-center">
          <h2 className="font-heading text-base font-semibold">No applications yet</h2>
          <p className="max-w-sm text-sm text-muted-foreground">
            Add the ones you are working on, and the ones that already ended, to start tracking
            them here.
          </p>
        </div>
      )}
      {rows.length > 0 && (
        <DndContext sensors={sensors} onDragEnd={(event) => void onDragEnd(event)}>
          <div className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-4">
            {STAGES.map((stage) => (
              <Column
                key={stage}
                id={stage}
                title={STAGE_LABELS[stage]}
                applications={open.filter((row) => row.stage === stage)}
                draggable={canWrite}
              />
            ))}
            <Column id={CLOSED} title="Closed" applications={closed} draggable={canWrite} />
          </div>
        </DndContext>
      )}
      <OutcomeDialog
        application={closing}
        onCancel={() => setClosing(null)}
        onPick={(outcome) => {
          if (closing) move.mutate({ id: closing.id, outcome });
          setClosing(null);
        }}
      />
    </div>
  );
}
