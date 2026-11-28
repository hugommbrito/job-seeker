import { useState } from "react";
import { useNavigate } from "react-router";

import { type Profile, useProfile, useUpdateProfile } from "@/api/profile";
import {
  FiltersSection,
  HomeSection,
  NotificationsSection,
  TimezoneSection,
  TracksSection,
} from "@/components/settings/Sections";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface Step {
  title: string;
  description: string;
  render: (profile: Profile, next: () => void) => React.ReactNode;
}

const NEXT = "Save and continue";

// Keyed on the step, so each form starts from the profile as it is now.
const STEPS: Step[] = [
  {
    title: "Where you are",
    description: "Reminders and quiet hours follow your own clock.",
    render: (profile, next) => <TimezoneSection profile={profile} submitLabel={NEXT} onSaved={next} />,
  },
  {
    title: "What you are looking for",
    description: "Add one track per kind of role. You can add more later.",
    render: (_profile, next) => <TracksSection submitLabel="Continue" onSaved={next} />,
  },
  {
    title: "What rules a posting out",
    description: "All optional. Nothing is ruled out on a fact the posting does not state.",
    render: (profile, next) => <FiltersSection profile={profile} submitLabel={NEXT} onSaved={next} />,
  },
  {
    title: "Where you would commute from",
    description: "Optional, and it never leaves this server.",
    render: (profile, next) => <HomeSection profile={profile} submitLabel={NEXT} onSaved={next} />,
  },
  {
    title: "How you hear from the app",
    description: "Reminders appear in the app. A phone channel can be linked in Settings.",
    render: (profile, next) => <NotificationsSection profile={profile} submitLabel={NEXT} onSaved={next} />,
  },
];

export function WelcomePage() {
  const profile = useProfile();
  const finish = useUpdateProfile();
  const navigate = useNavigate();
  const [index, setIndex] = useState(0);

  if (!profile.data) {
    return <p className="p-4 text-sm text-muted-foreground">Loading…</p>;
  }

  function done() {
    finish.mutate({ onboarded: true }, { onSuccess: () => void navigate("/board") });
  }

  const step = STEPS[index];
  const last = index === STEPS.length - 1;
  const next = () => (last ? done() : setIndex(index + 1));

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-4">
      <p className="text-sm text-muted-foreground">
        Setting up, step {index + 1} of {STEPS.length}
      </p>
      {step && (
        <Card key={index}>
          <CardHeader>
            <CardTitle>{step.title}</CardTitle>
            <CardDescription>{step.description}</CardDescription>
          </CardHeader>
          <CardContent>{step.render(profile.data, next)}</CardContent>
        </Card>
      )}
      {finish.isError && (
        <p role="alert" className="text-sm text-destructive">
          {finish.error.message}
        </p>
      )}
      <div className="flex justify-between gap-2">
        <Button variant="ghost" disabled={index === 0} onClick={() => setIndex(index - 1)}>
          Back
        </Button>
        <Button variant="ghost" onClick={done}>
          Skip the rest
        </Button>
      </div>
    </div>
  );
}
