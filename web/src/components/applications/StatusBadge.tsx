import { Badge } from "@/components/ui/badge";
import { OUTCOME_LABELS, STAGE_LABELS, type Outcome, type Stage } from "@/lib/stages";

/** The stage an application reached, and how it ended if it has. */
export function StatusBadge({ stage, outcome }: { stage: Stage; outcome: Outcome | null }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      <Badge variant="secondary">{STAGE_LABELS[stage]}</Badge>
      {outcome && <Badge variant="destructive">{OUTCOME_LABELS[outcome]}</Badge>}
    </span>
  );
}
