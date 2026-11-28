import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { type ApplicationDetail, errorMessage } from "@/api/applications";
import { api, ApiError } from "@/api/client";
import type { components } from "@/api/schema";

export type Capture = components["schemas"]["CaptureOut"];
export type Proposal = components["schemas"]["Proposal"];
export type CaptureSave = components["schemas"]["CaptureSaveIn"];

const DRAFTS_KEY = ["captures"] as const;
const captureKey = (id: number) => ["capture", id] as const;

function fail(response: Response, error: unknown, fallback: string): never {
  throw new ApiError(response.status, errorMessage(error, fallback));
}

export function useDrafts() {
  return useQuery({
    queryKey: DRAFTS_KEY,
    queryFn: async (): Promise<Capture[]> => {
      const { data, error, response } = await api.GET("/api/captures");
      if (!data) fail(response, error, "Could not load the captures.");
      return data;
    },
  });
}

/** One capture, asked for again every second and a half while the model is reading it. */
export function useCapture(id: number) {
  return useQuery({
    queryKey: captureKey(id),
    queryFn: async (): Promise<Capture> => {
      const { data, error, response } = await api.GET("/api/captures/{capture_id}", {
        params: { path: { capture_id: id } },
      });
      if (!data) fail(response, error, "Could not load the capture.");
      return data;
    },
    refetchInterval: (query) =>
      query.state.data?.extraction_status === "pending" ? 1500 : false,
  });
}

export function useCreateCapture() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { text: string; url: string }): Promise<Capture> => {
      const { data, error, response } = await api.POST("/api/captures", { body });
      if (!data) fail(response, error, "Could not keep the posting.");
      return data;
    },
    onSuccess: (capture) => {
      queryClient.setQueryData(captureKey(capture.id), capture);
      void queryClient.invalidateQueries({ queryKey: DRAFTS_KEY });
    },
  });
}

export function useReadAgain(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<Capture> => {
      const { data, error, response } = await api.POST("/api/captures/{capture_id}/extract", {
        params: { path: { capture_id: id } },
      });
      if (!data) fail(response, error, "Could not ask for a new reading.");
      return data;
    },
    onSuccess: (capture) => queryClient.setQueryData(captureKey(id), capture),
  });
}

export function useSaveCapture(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: CaptureSave): Promise<ApplicationDetail> => {
      const { data, error, response } = await api.POST("/api/captures/{capture_id}/save", {
        params: { path: { capture_id: id } },
        body,
      });
      if (!data) fail(response, error, "Could not save the application.");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DRAFTS_KEY });
      void queryClient.invalidateQueries({ queryKey: ["applications"] });
      void queryClient.invalidateQueries({ queryKey: captureKey(id) });
    },
  });
}

export function useDiscardCapture() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number): Promise<void> => {
      const { error, response } = await api.DELETE("/api/captures/{capture_id}", {
        params: { path: { capture_id: id } },
      });
      if (!response.ok) fail(response, error, "Could not discard the capture.");
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: DRAFTS_KEY }),
  });
}
