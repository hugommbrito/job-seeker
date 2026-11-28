import { Navigate } from "react-router";

import { useProfile } from "@/api/profile";
import { useCanWrite } from "@/auth/user";

/** The landing route: the wizard until it has been finished once, then the board. */
export function StartPage() {
  const profile = useProfile();
  const canWrite = useCanWrite();
  if (profile.isPending) return null;
  const welcome = canWrite && profile.data && !profile.data.onboarded;
  return <Navigate to={welcome ? "/welcome" : "/board"} replace />;
}
