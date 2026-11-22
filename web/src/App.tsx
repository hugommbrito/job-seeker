import { useSession } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { HomePage } from "@/pages/HomePage";
import { LoginPage } from "@/pages/LoginPage";

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
  return session.data ? <HomePage user={session.data} /> : <LoginPage />;
}
