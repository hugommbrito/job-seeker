import { useQuery } from "@tanstack/react-query";

import { api, ApiError, type Profile, type User } from "@/api/client";
import { useLogout } from "@/auth/session";
import { Button } from "@/components/ui/button";

async function fetchProfile(): Promise<Profile> {
  const { data, response } = await api.GET("/api/profile");
  if (!data) throw new ApiError(response.status, "Could not load the profile.");
  return data;
}

export function HomePage({ user }: { user: User }) {
  const logout = useLogout();
  const profile = useQuery({ queryKey: ["profile"], queryFn: fetchProfile });

  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex items-center justify-between gap-4 border-b px-4 py-3">
        <span className="font-heading font-semibold">job-seeker</span>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">{user.email}</span>
          <span className="rounded-md bg-muted px-2 py-0.5 text-xs">{user.role}</span>
          <Button
            variant="outline"
            size="sm"
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
          >
            Sign out
          </Button>
        </div>
      </header>
      <main className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
        <h1 className="font-heading text-xl font-semibold">Nothing here yet</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          Applications you track will appear here.
        </p>
        {profile.data && (
          <p className="text-xs text-muted-foreground">Timezone: {profile.data.timezone}</p>
        )}
      </main>
    </div>
  );
}
