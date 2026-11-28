import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { errorMessage } from "@/api/applications";
import { api, ApiError } from "@/api/client";
import type { components } from "@/api/schema";

export type AppNotification = components["schemas"]["NotificationOut"];
export type Channels = components["schemas"]["ChannelsOut"];

const NOTIFICATIONS_KEY = ["notifications"] as const;
const CHANNELS_KEY = ["channels"] as const;

function fail(response: Response, error: unknown, fallback: string): never {
  throw new ApiError(response.status, errorMessage(error, fallback));
}

export function useNotifications() {
  return useQuery({
    queryKey: NOTIFICATIONS_KEY,
    queryFn: async () => {
      const { data, error, response } = await api.GET("/api/notifications");
      if (!data) fail(response, error, "Could not load notifications.");
      return data;
    },
    // Reminders are created in the background; a minute is soon enough to see them.
    refetchInterval: 60_000,
  });
}

export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (ids?: number[]) => {
      const { error, response } = await api.POST("/api/notifications/read", {
        body: { ids: ids ?? null },
      });
      if (!response.ok) fail(response, error, "Could not mark as read.");
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY }),
  });
}

export function useChannels() {
  return useQuery({
    queryKey: CHANNELS_KEY,
    queryFn: async (): Promise<Channels> => {
      const { data, error, response } = await api.GET("/api/channels");
      if (!data) fail(response, error, "Could not load the channels.");
      return data;
    },
    // While a link is open, watch for the bot to confirm it.
    refetchInterval: (query) => (query.state.data?.telegram.linking ? 3000 : false),
  });
}

export function useLinkTelegram() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST("/api/channels/telegram/link");
      if (!data) fail(response, error, "Could not start linking.");
      return data;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CHANNELS_KEY }),
  });
}

export function useUnlinkTelegram() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await api.DELETE("/api/channels/telegram");
      if (!response.ok) fail(response, error, "Could not unlink.");
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CHANNELS_KEY }),
  });
}

export function useTestTelegram() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST("/api/channels/telegram/test");
      if (!data) fail(response, error, "Could not send a test.");
      return data;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY }),
  });
}
