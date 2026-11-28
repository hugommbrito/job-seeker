import { createContext, useContext } from "react";

import type { User } from "@/api/client";

export const UserContext = createContext<User | null>(null);

/** The signed-in user. Only rendered below the session gate, so it is always set there. */
export function useUser(): User {
  const user = useContext(UserContext);
  if (!user) throw new Error("useUser is only available while signed in.");
  return user;
}

/**
 * Whether the signed-in account may change anything. The server refuses every write from the
 * demo account; hiding the controls just spares the guest a button that always says no.
 */
export function useCanWrite(): boolean {
  return useUser().role !== "demo";
}
