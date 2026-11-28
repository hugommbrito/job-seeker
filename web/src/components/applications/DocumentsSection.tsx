import { FileIcon, Trash2Icon } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import {
  type ApplicationDetail,
  type DocumentKind,
  documentUrl,
  useDeleteDocument,
  useUploadDocument,
} from "@/api/applications";
import { useCanWrite } from "@/auth/user";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { formatInstant } from "@/lib/dates";

const KIND_LABELS: Record<DocumentKind, string> = {
  cv: "CV",
  cover_letter: "Cover letter",
  email: "Email",
  other: "Other",
};

const ACCEPT = ".pdf,.doc,.docx,.odt,.rtf,.txt,.md,.html,.htm,.eml,.png,.jpg,.jpeg";

function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentsSection({ application }: { application: ApplicationDetail }) {
  const canWrite = useCanWrite();
  const upload = useUploadDocument(application.id);
  const remove = useDeleteDocument(application.id);
  const [kind, setKind] = useState<DocumentKind>("cv");
  const [chosen, setChosen] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const file = input.current?.files?.[0];
    if (!file) return;
    upload.mutate(
      { file, kind },
      {
        onSuccess: () => {
          if (input.current) input.current.value = "";
          setChosen(false);
        },
      },
    );
  }

  return (
    <div className="flex flex-col gap-3 text-sm">
      {application.documents.length === 0 && (
        <p className="text-muted-foreground">No documents yet.</p>
      )}
      <ul className="flex flex-col gap-2">
        {application.documents.map((document) => (
          <li key={document.id} className="flex items-center justify-between gap-2">
            <a
              href={documentUrl(application.id, document.id)}
              download={document.filename}
              className="flex min-w-0 items-center gap-2 underline-offset-4 hover:underline"
            >
              <FileIcon className="size-4 shrink-0" />
              <span className="truncate">{document.filename}</span>
            </a>
            <span className="flex shrink-0 items-center gap-2 text-muted-foreground">
              {KIND_LABELS[document.kind]} · {size(document.size)} ·{" "}
              {formatInstant(document.created_at)}
              {canWrite && (
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Delete ${document.filename}`}
                  onClick={() => remove.mutate(document.id)}
                >
                  <Trash2Icon />
                </Button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {canWrite && (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-2 rounded-lg border p-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="document-file" className="text-xs">
              File (up to 10 MB)
            </Label>
            <Input
              id="document-file"
              ref={input}
              type="file"
              accept={ACCEPT}
              onChange={(event) => setChosen(Boolean(event.target.files?.length))}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="document-kind" className="text-xs">
              Kind
            </Label>
            <NativeSelect
              id="document-kind"
              value={kind}
              onChange={(event) => setKind(event.target.value as DocumentKind)}
            >
              {(Object.keys(KIND_LABELS) as DocumentKind[]).map((value) => (
                <NativeSelectOption key={value} value={value}>
                  {KIND_LABELS[value]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <Button type="submit" size="sm" disabled={!chosen || upload.isPending}>
            {upload.isPending ? "Uploading…" : "Upload"}
          </Button>
          {upload.isError && (
            <p role="alert" className="w-full text-destructive">
              {upload.error.message}
            </p>
          )}
        </form>
      )}
    </div>
  );
}
