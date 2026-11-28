import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router";

import { useCreateCapture, useDrafts } from "@/api/captures";
import { useCanWrite } from "@/auth/user";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatInstant } from "@/lib/dates";

// Matches the server's limit: a longer paste is almost always a whole page, not a posting.
const MAX_CHARS = 50_000;

function Drafts() {
  const drafts = useDrafts();
  if (!drafts.data || drafts.data.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Not saved yet</CardTitle>
        <CardDescription>Postings you pasted and have not reviewed.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-1 text-sm">
          {drafts.data.map((draft) => (
            <li key={draft.id}>
              <Link to={`/capture/${draft.id}`} className="underline underline-offset-4">
                {draft.proposal?.title || draft.description_text.slice(0, 80) || "Untitled"}
              </Link>{" "}
              <span className="text-muted-foreground">{formatInstant(draft.created_at)}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function CapturePage() {
  const create = useCreateCapture();
  const canWrite = useCanWrite();
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      { text, url },
      { onSuccess: (capture) => void navigate(`/capture/${capture.id}`) },
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4">
      <h1 className="font-heading text-lg font-semibold">Add a posting</h1>
      {canWrite ? (
        <Card>
          <CardHeader>
            <CardTitle>Paste the posting</CardTitle>
            <CardDescription>
              Copy the whole posting from the page and paste it here. It is read in the
              background; you review every field before anything is saved.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="flex flex-col gap-3">
              <Label htmlFor="capture-text">Posting text</Label>
              <Textarea
                id="capture-text"
                required
                rows={12}
                maxLength={MAX_CHARS}
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
              <Label htmlFor="capture-url">Where it was posted (optional)</Label>
              <Input
                id="capture-url"
                type="url"
                placeholder="https://"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
              />
              {create.isError && (
                <p role="alert" className="text-sm text-destructive">
                  {create.error.message}
                </p>
              )}
              <div>
                <Button type="submit" disabled={create.isPending || !text.trim()}>
                  {create.isPending ? "Keeping it…" : "Read the posting"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : (
        <p className="text-sm text-muted-foreground">Adding postings is not part of the demo.</p>
      )}
      <Drafts />
    </div>
  );
}
