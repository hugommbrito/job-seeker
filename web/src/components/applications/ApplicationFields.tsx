import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import type { ApplicationDraft } from "@/lib/draft";
import { OUTCOME_LABELS, OUTCOMES, STAGE_LABELS, STAGES } from "@/lib/stages";

interface Props {
  value: ApplicationDraft;
  onChange: (next: ApplicationDraft) => void;
  /** Show the fields for an application that already happened: outcome and its dates. */
  pastFields?: boolean;
  /** The stage is chosen here on creation; afterwards it changes through the move menu. */
  stageField?: boolean;
}

export function ApplicationFields({
  value,
  onChange,
  pastFields = true,
  stageField = true,
}: Props) {
  function field(name: keyof ApplicationDraft) {
    return {
      id: `application-${name}`,
      name,
      value: value[name],
      onChange: (event: { target: { value: string } }) =>
        onChange({ ...value, [name]: event.target.value }),
    };
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-2">
        <Label htmlFor="application-company_name">Company</Label>
        <Input required maxLength={200} autoComplete="off" {...field("company_name")} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="application-role_title">Role</Label>
        <Input required maxLength={300} autoComplete="off" {...field("role_title")} />
      </div>
      {stageField && (
        <div className="flex flex-col gap-2">
          <Label htmlFor="application-stage">Stage</Label>
          <NativeSelect className="w-full" {...field("stage")}>
            {STAGES.map((stage) => (
              <NativeSelectOption key={stage} value={stage}>
                {STAGE_LABELS[stage]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
      )}
      <div className="flex flex-col gap-2">
        <Label htmlFor="application-applied_at">Applied on</Label>
        <Input type="date" {...field("applied_at")} />
      </div>
      <div className="flex flex-col gap-2 sm:col-span-2">
        <Label htmlFor="application-posting_url">Posting URL</Label>
        <Input type="url" placeholder="https://" maxLength={2000} {...field("posting_url")} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="application-location">Location</Label>
        <Input maxLength={200} {...field("location")} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="application-source">Found through</Label>
        <Input maxLength={100} placeholder="Referral, company site…" {...field("source")} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="application-next_action">Next action</Label>
        <Input maxLength={300} {...field("next_action")} />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="application-next_action_due">Next action due</Label>
        <Input type="date" {...field("next_action_due")} />
      </div>
      <div className="flex flex-col gap-2 sm:col-span-2">
        <Label htmlFor="application-notes">Notes</Label>
        <Textarea rows={3} {...field("notes")} />
      </div>
      {pastFields && (
        <fieldset className="grid gap-4 rounded-lg border p-3 sm:col-span-2 sm:grid-cols-3">
          <legend className="px-1 text-xs text-muted-foreground">
            Recording one that already happened
          </legend>
          <div className="flex flex-col gap-2">
            <Label htmlFor="application-outcome">Outcome</Label>
            <NativeSelect className="w-full" {...field("outcome")}>
              <NativeSelectOption value="">Still open</NativeSelectOption>
              {OUTCOMES.map((outcome) => (
                <NativeSelectOption key={outcome} value={outcome}>
                  {OUTCOME_LABELS[outcome]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="application-last_interview_at">Last interview</Label>
            <Input type="date" {...field("last_interview_at")} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="application-closed_on">Closed on</Label>
            <Input type="date" disabled={!value.outcome} {...field("closed_on")} />
          </div>
        </fieldset>
      )}
    </div>
  );
}
