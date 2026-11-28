import { Link, Route, Routes } from "react-router";

import { useSession } from "@/auth/session";
import { UserContext } from "@/auth/user";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { ApplicationPage } from "@/pages/ApplicationPage";
import { ApplicationsPage } from "@/pages/ApplicationsPage";
import { BoardPage } from "@/pages/BoardPage";
import { CapturePage } from "@/pages/CapturePage";
import { LoginPage } from "@/pages/LoginPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { ReviewCapturePage } from "@/pages/ReviewCapturePage";
import { SettingsPage } from "@/pages/SettingsPage";
import { StartPage } from "@/pages/StartPage";
import { WelcomePage } from "@/pages/WelcomePage";

function NotFound() {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-center">
      <h1 className="font-heading text-lg font-semibold">Nothing here</h1>
      <Link to="/board" className="text-sm underline">
        Back to the board
      </Link>
    </div>
  );
}

export function App() {
  const session = useSession();

  if (session.isPending) {
    return (
      <p className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Loading…
      </p>
    );
  }
  if (session.isError) {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center gap-3">
        <p role="alert" className="text-sm">
          Could not reach the server.
        </p>
        <Button variant="outline" onClick={() => void session.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  if (!session.data) return <LoginPage />;

  return (
    <UserContext.Provider value={session.data}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<StartPage />} />
          <Route path="board" element={<BoardPage />} />
          <Route path="applications" element={<ApplicationsPage />} />
          <Route path="applications/:id" element={<ApplicationPage />} />
          <Route path="capture" element={<CapturePage />} />
          <Route path="capture/:id" element={<ReviewCapturePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="welcome" element={<WelcomePage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </UserContext.Provider>
  );
}
