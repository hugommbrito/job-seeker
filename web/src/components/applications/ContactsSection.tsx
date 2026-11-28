import { Trash2Icon } from "lucide-react";
import { type FormEvent, useState } from "react";

import {
  type ApplicationDetail,
  type ContactInput,
  useAddContact,
  useDeleteContact,
} from "@/api/applications";
import { useCanWrite } from "@/auth/user";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const EMPTY: ContactInput = { name: "", role: "", email: "", phone: "", profile_url: "", notes: "" };

export function ContactsSection({ application }: { application: ApplicationDetail }) {
  const canWrite = useCanWrite();
  const add = useAddContact(application.id);
  const remove = useDeleteContact(application.id);
  const [draft, setDraft] = useState<ContactInput>(EMPTY);

  function submit(event: FormEvent) {
    event.preventDefault();
    add.mutate(draft, { onSuccess: () => setDraft(EMPTY) });
  }

  function field(name: keyof ContactInput) {
    return {
      id: `contact-${name}`,
      value: draft[name] ?? "",
      onChange: (event: { target: { value: string } }) =>
        setDraft({ ...draft, [name]: event.target.value }),
    };
  }

  return (
    <div className="flex flex-col gap-3 text-sm">
      {application.contacts.length === 0 && (
        <p className="text-muted-foreground">No contacts yet.</p>
      )}
      <ul className="flex flex-col gap-2">
        {application.contacts.map((contact) => (
          <li key={contact.id} className="flex items-start justify-between gap-2">
            <div className="flex min-w-0 flex-col">
              <span className="font-medium">
                {contact.name}
                {contact.role && <span className="font-normal text-muted-foreground">, {contact.role}</span>}
              </span>
              <span className="flex flex-wrap gap-x-3 text-muted-foreground">
                {contact.email && (
                  <a className="underline" href={`mailto:${contact.email}`}>
                    {contact.email}
                  </a>
                )}
                {contact.phone && <span>{contact.phone}</span>}
                {contact.profile_url && (
                  <a
                    className="underline"
                    href={contact.profile_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Profile
                  </a>
                )}
              </span>
            </div>
            {canWrite && (
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`Remove ${contact.name}`}
                onClick={() => remove.mutate(contact.id)}
              >
                <Trash2Icon />
              </Button>
            )}
          </li>
        ))}
      </ul>
      {canWrite && (
        <form onSubmit={submit} className="grid gap-2 rounded-lg border p-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="contact-name" className="text-xs">
              Name
            </Label>
            <Input required maxLength={200} {...field("name")} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="contact-role" className="text-xs">
              Role
            </Label>
            <Input maxLength={200} placeholder="Recruiter, hiring manager…" {...field("role")} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="contact-email" className="text-xs">
              Email
            </Label>
            <Input type="email" maxLength={254} {...field("email")} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="contact-phone" className="text-xs">
              Phone
            </Label>
            <Input type="tel" maxLength={50} {...field("phone")} />
          </div>
          <div className="flex flex-col gap-1 sm:col-span-2">
            <Label htmlFor="contact-profile_url" className="text-xs">
              Profile URL
            </Label>
            <Input type="url" maxLength={500} placeholder="https://" {...field("profile_url")} />
          </div>
          {add.isError && (
            <p role="alert" className="text-destructive sm:col-span-2">
              {add.error.message}
            </p>
          )}
          <div className="sm:col-span-2">
            <Button type="submit" size="sm" disabled={add.isPending}>
              Add contact
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
