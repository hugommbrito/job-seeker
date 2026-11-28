import { PlusIcon } from "lucide-react";
import { type FormEvent, useState } from "react";

import { useCreateApplication } from "@/api/applications";
import { ApplicationFields } from "@/components/applications/ApplicationFields";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { type ApplicationDraft, draftToInput, EMPTY_DRAFT } from "@/lib/draft";

/** Add an application by hand: a new one, or one that already happened and ended. */
export function NewApplicationDialog() {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<ApplicationDraft>(EMPTY_DRAFT);
  const create = useCreateApplication();

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(draftToInput(draft), {
      onSuccess: () => {
        setOpen(false);
        setDraft(EMPTY_DRAFT);
      },
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) create.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm">
          <PlusIcon /> Add application
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>Add an application</DialogTitle>
            <DialogDescription>
              Only the company and the role are required. Everything else can be added later.
            </DialogDescription>
          </DialogHeader>
          <ApplicationFields value={draft} onChange={setDraft} />
          {create.isError && (
            <p role="alert" className="text-sm text-destructive">
              {create.error.message}
            </p>
          )}
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
