import type { ReactNode } from "react";

import { useProfile } from "@/api/profile";
import { useCanWrite } from "@/auth/user";
import {
  FiltersSection,
  HomeSection,
  NotificationsSection,
  TimezoneSection,
  TracksSection,
} from "@/components/settings/Sections";
import { TelegramSection } from "@/components/settings/TelegramSection";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function SettingsPage() {
  const profile = useProfile();
  const canWrite = useCanWrite();

  if (profile.isPending) return <p className="p-4 text-sm text-muted-foreground">Loading…</p>;
  if (profile.isError) {
    return (
      <p role="alert" className="p-4 text-sm">
        {profile.error.message}
      </p>
    );
  }
  if (!canWrite) {
    return <p className="p-4 text-sm text-muted-foreground">Settings are not part of the demo.</p>;
  }
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4">
      <h1 className="font-heading text-lg font-semibold">Settings</h1>
      <Section title="Tracks">
        <TracksSection />
      </Section>
      <Section title="Filters">
        <FiltersSection profile={profile.data} />
      </Section>
      <Section title="Notifications">
        <NotificationsSection profile={profile.data} />
      </Section>
      <Section title="Phone">
        <TelegramSection />
      </Section>
      <Section title="Home">
        <HomeSection profile={profile.data} />
      </Section>
      <Section title="Timezone">
        <TimezoneSection profile={profile.data} />
      </Section>
    </div>
  );
}
