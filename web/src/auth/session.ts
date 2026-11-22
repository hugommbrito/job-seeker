import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, type User } from "@/api/client";

const SESSION_KEY = ["session"] as const;

async function fetchSession(): Promise<User | null> {
  const { data, response } = await api.GET("/api/auth/me");
  if (response.status === 401) return null;
  if (!data) throw new ApiError(response.status, "Could not load the session.");
  return data;
}

/** The signed-in user, `null` when nobody is signed in. */
export function useSession() {
  return useQuery({
    queryKey: SESSION_KEY,
    queryFn: fetchSession,
    staleTime: Infinity,
    retry: false,
  });
}

/**
 * Forget the session and everything fetched during it.
 *
 * Cached responses belong to the person who just left; the next person to sign in on this
 * browser must not see a frame of them.
 */
export function endSession(queryClient: QueryClient): void {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== SESSION_KEY[0] });
  queryClient.setQueryData(SESSION_KEY, null);
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (credentials: { email: string; password: string }): Promise<User> => {
      const { data, error, response } = await api.POST("/api/auth/login", { body: credentials });
      if (!data) throw new ApiError(response.status, error?.detail ?? "Sign-in failed.");
      return data;
    },
    onSuccess: (user) => queryClient.setQueryData(SESSION_KEY, user),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<void> => {
      await api.POST("/api/auth/logout");
    },
    // Also when the request failed: the person asked to leave, so this side lets go either way.
    onSettled: () => endSession(queryClient),
  });
}
