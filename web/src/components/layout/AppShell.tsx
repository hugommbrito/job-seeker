import { BellIcon } from "lucide-react";
import { NavLink, Outlet } from "react-router";

import { useNotifications } from "@/api/notifications";

import { useLogout } from "@/auth/session";
import { useUser } from "@/auth/user";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/board", label: "Board" },
  { to: "/applications", label: "Applications" },
  { to: "/capture", label: "Add posting" },
  { to: "/settings", label: "Settings" },
];

function Bell() {
  const notifications = useNotifications();
  const unread = notifications.data?.unread ?? 0;
  return (
    <NavLink
      to="/notifications"
      aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
      className="relative rounded-md p-1.5 hover:bg-muted"
    >
      <BellIcon className="size-4" />
      {unread > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-4 rounded-full bg-destructive px-1 text-center text-[10px] leading-4 text-white">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </NavLink>
  );
}

export function AppShell() {
  const user = useUser();
  const logout = useLogout();

  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b px-4 py-2">
        <div className="flex items-center gap-4">
          <span className="font-heading font-semibold">job-seeker</span>
          <nav aria-label="Main" className="flex gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-2 py-1 text-sm hover:bg-muted",
                    isActive && "bg-muted font-medium",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Bell />
          <span className="hidden text-muted-foreground sm:inline">{user.email}</span>
          {user.role === "demo" && (
            <span className="rounded-md bg-muted px-2 py-0.5 text-xs">Demo, read only</span>
          )}
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
      <main className="flex flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  );
}
