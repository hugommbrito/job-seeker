import { EllipsisIcon } from "lucide-react";

import { type Application, useTransition } from "@/api/applications";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { OUTCOME_LABELS, OUTCOMES, STAGE_LABELS, STAGES } from "@/lib/stages";

/**
 * Every column change a card can make, from a menu. Dragging does the same on the board; this
 * is the way that works with a keyboard, a screen reader and a phone.
 */
export function MoveMenu({ application }: { application: Application }) {
  const move = useTransition();
  const open = application.outcome === null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`Move ${application.company_name}, ${application.role_title}`}
          onClick={(event) => event.stopPropagation()}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <EllipsisIcon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" onClick={(event) => event.stopPropagation()}>
        <DropdownMenuLabel>Move to</DropdownMenuLabel>
        {STAGES.filter((stage) => stage !== application.stage || !open).map((stage) => (
          <DropdownMenuItem
            key={stage}
            onSelect={async () => {
              if (!open) await move.mutateAsync({ id: application.id, reopen: true });
              move.mutate({ id: application.id, stage });
            }}
          >
            {STAGE_LABELS[stage]}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        {open ? (
          <>
            <DropdownMenuLabel>Close as</DropdownMenuLabel>
            {OUTCOMES.map((outcome) => (
              <DropdownMenuItem
                key={outcome}
                onSelect={() => move.mutate({ id: application.id, outcome })}
              >
                {OUTCOME_LABELS[outcome]}
              </DropdownMenuItem>
            ))}
          </>
        ) : (
          <DropdownMenuItem onSelect={() => move.mutate({ id: application.id, reopen: true })}>
            Reopen
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
