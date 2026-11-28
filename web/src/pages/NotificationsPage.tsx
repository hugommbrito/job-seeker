import { Link } from "react-router";

import { useMarkRead, useNotifications } from "@/api/notifications";
import { useCanWrite } from "@/auth/user";
import { Button } from "@/components/ui/button";
import { formatInstant } from "@/lib/dates";
import { cn } from "@/lib/utils";

/** Only app paths become links: a notification never sends anyone off the site. */
function isAppPath(link: string): boolean {
  return link.startsWith("/") && !link.startsWith("//");
}

export function NotificationsPage() {
  const notifications = useNotifications();
  const markRead = useMarkRead();
  const canWrite = useCanWrite();
  const items = notifications.data?.items ?? [];

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="font-heading text-lg font-semibold">Notifications</h1>
        {canWrite && (notifications.data?.unread ?? 0) > 0 && (
          <Button variant="outline" size="sm" onClick={() => markRead.mutate(undefined)}>
            Mark all as read
          </Button>
        )}
      </div>
      {notifications.isError && (
        <p role="alert" className="text-sm text-destructive">
          {notifications.error.message}
        </p>
      )}
      {notifications.isSuccess && items.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">Nothing yet.</p>
      )}
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li
            key={item.id}
            className={cn("rounded-lg border p-3 text-sm", !item.read && "border-primary/40 bg-muted/40")}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-medium">{item.title}</span>
              <span className="shrink-0 text-xs text-muted-foreground">{formatInstant(item.created_at)}</span>
            </div>
            {item.body && <p className="mt-1 whitespace-pre-wrap">{item.body}</p>}
            {item.link && isAppPath(item.link) && (
              <Link
                to={item.link}
                className="mt-1 inline-block underline underline-offset-4"
                onClick={() => canWrite && !item.read && markRead.mutate([item.id])}
              >
                Open
              </Link>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
