import { useMutation, useQueryClient } from "@tanstack/react-query";
import { UploadIcon } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import { api } from "@/api/client";
import type { components, paths } from "@/api/schema";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type ImportResult = components["schemas"]["ImportOut"];
type ImportBody =
  paths["/api/applications/import"]["post"]["requestBody"]["content"]["multipart/form-data"];

/** Applications that happened before the app, from a CSV or JSON file. */
export function ImportDialog() {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [chosen, setChosen] = useState(false);
  const upload = useMutation({
    mutationFn: async (file: File): Promise<ImportResult> => {
      const form = new FormData();
      form.append("file", file);
      const { data, error } = await api.POST("/api/applications/import", {
        body: form as unknown as ImportBody,
      });
      // A refused file still answers with the list of problems.
      const result = data ?? (error as ImportResult | undefined);
      if (!result || !("errors" in result)) throw new Error("The file could not be imported.");
      return result;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const file = input.current?.files?.[0];
    if (file) upload.mutate(file);
  }

  const result = upload.data;
  return (
    <Dialog onOpenChange={(open) => !open && upload.reset()}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <UploadIcon /> Import
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import past applications</DialogTitle>
          <DialogDescription>
            A CSV file with a header row, or a JSON list. Columns: company_name and role_title
            (required), stage, outcome, applied_at, last_interview_at, closed_on, posting_url,
            location, source, notes, next_action, next_action_due. Dates are YYYY-MM-DD. If any
            row has a problem, nothing is imported; a row already imported is skipped.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Label htmlFor="import-file">File</Label>
          <Input
            id="import-file"
            ref={input}
            type="file"
            accept=".csv,.json"
            onChange={(event) => setChosen(Boolean(event.target.files?.length))}
          />
          <div>
            <Button type="submit" disabled={!chosen || upload.isPending}>
              {upload.isPending ? "Importing…" : "Import"}
            </Button>
          </div>
        </form>
        {upload.isError && (
          <p role="alert" className="text-sm text-destructive">
            {upload.error.message}
          </p>
        )}
        {result && result.errors.length === 0 && (
          <p role="status" className="text-sm">
            Imported {result.created}; {result.skipped} already there.
          </p>
        )}
        {result && result.errors.length > 0 && (
          <div role="alert" className="flex flex-col gap-1 text-sm text-destructive">
            <p>Nothing was imported:</p>
            <ul className="list-disc pl-5">
              {result.errors.slice(0, 20).map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
