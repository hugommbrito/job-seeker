import { Trash2Icon } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";

import {
  type CompleteHardFilters,
  completeHardFilters,
  type NotifySettings,
  type Profile,
  useCreateTrack,
  useDeleteTrack,
  useTracks,
  useUpdateProfile,
} from "@/api/profile";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { splitList, toggle } from "@/lib/lists";

/** What every section gets: the profile, and what its button says and does after saving. */
export interface SectionProps {
  profile: Profile;
  submitLabel?: string;
  onSaved?: () => void;
}

function Saving({
  error,
  pending,
  label,
  saved,
}: {
  error: Error | null;
  pending: boolean;
  label: string;
  saved: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button type="submit" disabled={pending}>
        {pending ? "Saving…" : label}
      </Button>
      {saved && !pending && !error && <span className="text-sm text-muted-foreground">Saved.</span>}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error.message}
        </p>
      )}
    </div>
  );
}

function Checks<T extends string>({
  name,
  options,
  value,
  onChange,
}: {
  name: string;
  options: [T, string][];
  value: T[];
  onChange: (next: T[]) => void;
}) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-2">
      {options.map(([option, label]) => {
        const id = `${name}-${option}`;
        return (
          <div key={option} className="flex items-center gap-2">
            <Checkbox
              id={id}
              checked={value.includes(option)}
              onCheckedChange={(on) => onChange(toggle(value, option, on === true))}
            />
            <Label htmlFor={id} className="font-normal">
              {label}
            </Label>
          </div>
        );
      })}
    </div>
  );
}

function Row({ label, htmlFor, children, hint }: { label: string; htmlFor?: string; children: ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      {htmlFor ? <Label htmlFor={htmlFor}>{label}</Label> : <span className="text-sm font-medium">{label}</span>}
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function zones(): string[] {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch {
    return [];
  }
}

export function TimezoneSection({ profile, submitLabel = "Save", onSaved }: SectionProps) {
  const update = useUpdateProfile();
  const [timezone, setTimezone] = useState(profile.timezone);
  const options = zones();

  function submit(event: FormEvent) {
    event.preventDefault();
    update.mutate({ timezone }, { onSuccess: onSaved });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Row
        label="Timezone"
        htmlFor="settings-timezone"
        hint="Reminders count days, and quiet hours run, in this timezone."
      >
        {options.length > 0 ? (
          <NativeSelect
            id="settings-timezone"
            className="w-full sm:w-80"
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
          >
            {options.map((zone) => (
              <NativeSelectOption key={zone} value={zone}>
                {zone}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        ) : (
          <Input id="settings-timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)} />
        )}
      </Row>
      <Saving error={update.error} pending={update.isPending} label={submitLabel} saved={update.isSuccess} />
    </form>
  );
}

export function TracksSection({ submitLabel, onSaved }: Omit<SectionProps, "profile">) {
  const tracks = useTracks();
  const create = useCreateTrack();
  const remove = useDeleteTrack();
  const [name, setName] = useState("");
  const [titles, setTitles] = useState("");
  const [summary, setSummary] = useState("");

  function add(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      { name, target_titles: splitList(titles), summary, active: true },
      {
        onSuccess: () => {
          setName("");
          setTitles("");
          setSummary("");
        },
      },
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        A track is one kind of role you are after. Postings will be judged against the track they
        fit best, so a person can look for more than one kind of job.
      </p>
      <ul className="flex flex-col gap-2">
        {tracks.data?.map((track) => (
          <li key={track.id} className="flex items-start justify-between gap-2 rounded-lg border p-2 text-sm">
            <div className="flex flex-col">
              <span className="font-medium">{track.name}</span>
              {track.target_titles.length > 0 && (
                <span className="text-muted-foreground">{track.target_titles.join(", ")}</span>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`Remove ${track.name}`}
              onClick={() => remove.mutate(track.id)}
            >
              <Trash2Icon />
            </Button>
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="flex flex-col gap-3 rounded-lg border p-3">
        <Row label="Track name" htmlFor="track-name">
          <Input id="track-name" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </Row>
        <Row label="Job titles" htmlFor="track-titles" hint="Separated by commas.">
          <Input id="track-titles" value={titles} onChange={(e) => setTitles(e.target.value)} />
        </Row>
        <Row label="What you would bring" htmlFor="track-summary">
          <Textarea id="track-summary" rows={3} maxLength={5000} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </Row>
        {create.isError && (
          <p role="alert" className="text-sm text-destructive">
            {create.error.message}
          </p>
        )}
        <div>
          <Button type="submit" variant="outline" disabled={create.isPending}>
            Add track
          </Button>
        </div>
      </form>
      {onSaved && (
        <div>
          <Button onClick={onSaved}>{submitLabel ?? "Continue"}</Button>
        </div>
      )}
    </div>
  );
}

const WORKPLACES: [CompleteHardFilters["workplace_types"][number], string][] = [
  ["remote", "Remote"],
  ["hybrid", "Hybrid"],
  ["onsite", "On site"],
];
const SENIORITY: [CompleteHardFilters["seniority"][number], string][] = [
  ["intern", "Intern"],
  ["junior", "Junior"],
  ["intermediate", "Intermediate"],
  ["senior", "Senior"],
  ["staff", "Staff"],
  ["principal", "Principal"],
  ["manager", "Manager"],
  ["director", "Director"],
];
const EMPLOYMENT: [CompleteHardFilters["employment_types"][number], string][] = [
  ["full_time", "Full time"],
  ["part_time", "Part time"],
  ["contract", "Contract"],
  ["temporary", "Temporary"],
  ["internship", "Internship"],
];

export function FiltersSection({ profile, submitLabel = "Save", onSaved }: SectionProps) {
  const update = useUpdateProfile();
  const hard = completeHardFilters(profile.hard);
  const [workplaces, setWorkplaces] = useState(hard.workplace_types);
  const [locations, setLocations] = useState(hard.locations.join(", "));
  const [floor, setFloor] = useState(hard.salary_floor ? String(hard.salary_floor.amount) : "");
  const [currency, setCurrency] = useState(hard.salary_floor?.currency ?? "CAD");
  const [period, setPeriod] = useState(hard.salary_floor?.period ?? "year");
  const [seniority, setSeniority] = useState(hard.seniority);
  const [employment, setEmployment] = useState(hard.employment_types);
  const [commute, setCommute] = useState(hard.max_commute_km == null ? "" : String(hard.max_commute_km));

  function submit(event: FormEvent) {
    event.preventDefault();
    update.mutate(
      {
        hard: {
          workplace_types: workplaces,
          locations: splitList(locations),
          salary_floor: floor ? { amount: floor, currency: currency.toUpperCase(), period } : null,
          seniority,
          employment_types: employment,
          max_commute_km: commute ? Number(commute) : null,
        },
      },
      { onSuccess: onSaved },
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        These rule a posting out only when it states the opposite. A posting that says nothing
        about a filter is never ruled out by it. Leave a filter empty to accept anything.
      </p>
      <Row label="Workplace">
        <Checks name="filter-workplace" options={WORKPLACES} value={workplaces} onChange={setWorkplaces} />
      </Row>
      <Row label="Locations" htmlFor="filter-locations" hint="Cities or regions, separated by commas.">
        <Input id="filter-locations" value={locations} onChange={(e) => setLocations(e.target.value)} />
      </Row>
      <div className="grid gap-3 sm:grid-cols-3">
        <Row label="Lowest salary" htmlFor="filter-floor">
          <Input id="filter-floor" inputMode="decimal" value={floor} onChange={(e) => setFloor(e.target.value)} />
        </Row>
        <Row label="Currency" htmlFor="filter-currency">
          <Input id="filter-currency" maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value)} />
        </Row>
        <Row label="Per" htmlFor="filter-period">
          <NativeSelect
            id="filter-period"
            className="w-full"
            value={period}
            onChange={(e) => setPeriod(e.target.value as typeof period)}
          >
            <NativeSelectOption value="year">Year</NativeSelectOption>
            <NativeSelectOption value="month">Month</NativeSelectOption>
            <NativeSelectOption value="hour">Hour</NativeSelectOption>
          </NativeSelect>
        </Row>
      </div>
      <Row label="Seniority">
        <Checks name="filter-seniority" options={SENIORITY} value={seniority} onChange={setSeniority} />
      </Row>
      <Row label="Employment">
        <Checks name="filter-employment" options={EMPLOYMENT} value={employment} onChange={setEmployment} />
      </Row>
      <Row label="Longest commute (km, straight line)" htmlFor="filter-commute">
        <Input id="filter-commute" inputMode="decimal" className="sm:w-40" value={commute} onChange={(e) => setCommute(e.target.value)} />
      </Row>
      <Saving error={update.error} pending={update.isPending} label={submitLabel} saved={update.isSuccess} />
    </form>
  );
}

export function HomeSection({ profile, submitLabel = "Save", onSaved }: SectionProps) {
  const update = useUpdateProfile();
  const [label, setLabel] = useState(profile.home?.label ?? "");
  const [latitude, setLatitude] = useState(profile.home ? String(profile.home.latitude) : "");
  const [longitude, setLongitude] = useState(profile.home ? String(profile.home.longitude) : "");
  const [locating, setLocating] = useState<string | null>(null);

  function useMyLocation() {
    if (!navigator.geolocation) {
      setLocating("This browser cannot share its location.");
      return;
    }
    setLocating("Asking the browser…");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLatitude(position.coords.latitude.toFixed(6));
        setLongitude(position.coords.longitude.toFixed(6));
        setLocating(null);
      },
      () => setLocating("The location was not shared."),
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const home = latitude && longitude ? { label, latitude, longitude } : null;
    update.mutate({ home }, { onSuccess: onSaved });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Used only to estimate commutes, on this server. It is never sent to a model or to anyone
        else. Leave it empty if you prefer.
      </p>
      <Row label="Name for it" htmlFor="home-label" hint="Shown only to you, such as a nearby intersection.">
        <Input id="home-label" maxLength={100} value={label} onChange={(e) => setLabel(e.target.value)} />
      </Row>
      <div className="grid gap-3 sm:grid-cols-2">
        <Row label="Latitude" htmlFor="home-latitude">
          <Input id="home-latitude" inputMode="decimal" value={latitude} onChange={(e) => setLatitude(e.target.value)} />
        </Row>
        <Row label="Longitude" htmlFor="home-longitude">
          <Input id="home-longitude" inputMode="decimal" value={longitude} onChange={(e) => setLongitude(e.target.value)} />
        </Row>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" onClick={useMyLocation}>
          Use my current location
        </Button>
        {locating && <span className="text-sm text-muted-foreground">{locating}</span>}
      </div>
      <Saving error={update.error} pending={update.isPending} label={submitLabel} saved={update.isSuccess} />
    </form>
  );
}

function clock(value: string | undefined, fallback: string): string {
  return value ? value.slice(0, 5) : fallback;
}

export function NotificationsSection({
  profile,
  submitLabel = "Save",
  onSaved,
  children,
}: SectionProps & { children?: ReactNode }) {
  const update = useUpdateProfile();
  const notify: NotifySettings = profile.notify;
  const [quiet, setQuiet] = useState(notify.quiet_hours != null);
  const [start, setStart] = useState(clock(notify.quiet_hours?.start, "22:00"));
  const [end, setEnd] = useState(clock(notify.quiet_hours?.end, "08:00"));
  const [days, setDays] = useState(String(notify.follow_up_after_days));
  const [nextAction, setNextAction] = useState(notify.remind_next_action);
  const [decision, setDecision] = useState(notify.remind_decision_due);
  const [quietApps, setQuietApps] = useState(notify.remind_quiet);

  function submit(event: FormEvent) {
    event.preventDefault();
    update.mutate(
      {
        notify: {
          quiet_hours: quiet ? { start, end } : null,
          follow_up_after_days: Number(days),
          remind_next_action: nextAction,
          remind_decision_due: decision,
          remind_quiet: quietApps,
        },
      },
      { onSuccess: onSaved },
    );
  }

  const toggles: [string, string, boolean, (on: boolean) => void][] = [
    ["remind-next", "When a next action is due", nextAction, setNextAction],
    ["remind-decision", "When the 45 days after a last interview have passed", decision, setDecision],
    ["remind-quiet", "When an application has had no news for a while", quietApps, setQuietApps],
  ];

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Row label="Remind me">
        <div className="flex flex-col gap-2">
          {toggles.map(([id, label, value, set]) => (
            <div key={id} className="flex items-center gap-2">
              <Checkbox id={id} checked={value} onCheckedChange={(on) => set(on === true)} />
              <Label htmlFor={id} className="font-normal">
                {label}
              </Label>
            </div>
          ))}
        </div>
      </Row>
      <Row label="No news for how many days" htmlFor="notify-days" hint="Between 3 and 90.">
        <Input id="notify-days" type="number" min={3} max={90} className="sm:w-28" value={days} onChange={(e) => setDays(e.target.value)} />
      </Row>
      <Row label="Quiet hours" hint="Nothing is pushed to your phone in this window; it waits until the end.">
        <div className="flex flex-wrap items-center gap-2">
          <Checkbox id="notify-quiet" checked={quiet} onCheckedChange={(on) => setQuiet(on === true)} />
          <Label htmlFor="notify-quiet" className="font-normal">
            From
          </Label>
          <Input aria-label="Quiet from" type="time" className="w-32" disabled={!quiet} value={start} onChange={(e) => setStart(e.target.value)} />
          <span className="text-sm">to</span>
          <Input aria-label="Quiet until" type="time" className="w-32" disabled={!quiet} value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </Row>
      {children}
      <Saving error={update.error} pending={update.isPending} label={submitLabel} saved={update.isSuccess} />
    </form>
  );
}
