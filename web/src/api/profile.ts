import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { errorMessage } from "@/api/applications";
import { api, ApiError } from "@/api/client";
import type { components } from "@/api/schema";

export type Profile = components["schemas"]["ProfileOut"];
export type ProfileChanges = components["schemas"]["ProfilePatch"];
export type HardFilters = components["schemas"]["HardFilters"];
export type NotifySettings = components["schemas"]["NotifySettings"];
export type Track = components["schemas"]["TrackOut"];
export type TrackInput = components["schemas"]["TrackIn"];

/** The filters with every list present: the server omits nothing, but the type allows it. */
export type CompleteHardFilters = {
  [K in keyof HardFilters]-?: Exclude<HardFilters[K], undefined>;
};

export function completeHardFilters(hard: HardFilters): CompleteHardFilters {
  return {
    workplace_types: hard.workplace_types ?? [],
    locations: hard.locations ?? [],
    salary_floor: hard.salary_floor ?? null,
    seniority: hard.seniority ?? [],
    employment_types: hard.employment_types ?? [],
    max_commute_km: hard.max_commute_km ?? null,
  };
}

const PROFILE_KEY = ["profile"] as const;
const TRACKS_KEY = ["tracks"] as const;

function fail(response: Response, error: unknown, fallback: string): never {
  throw new ApiError(response.status, errorMessage(error, fallback));
}

export function useProfile() {
  return useQuery({
    queryKey: PROFILE_KEY,
    queryFn: async (): Promise<Profile> => {
      const { data, error, response } = await api.GET("/api/profile");
      if (!data) fail(response, error, "Could not load the profile.");
      return data;
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ProfileChanges): Promise<Profile> => {
      const { data, error, response } = await api.PATCH("/api/profile", { body });
      if (!data) fail(response, error, "Could not save.");
      return data;
    },
    onSuccess: (profile) => queryClient.setQueryData(PROFILE_KEY, profile),
  });
}

export function useTracks() {
  return useQuery({
    queryKey: TRACKS_KEY,
    queryFn: async (): Promise<Track[]> => {
      const { data, error, response } = await api.GET("/api/tracks");
      if (!data) fail(response, error, "Could not load the tracks.");
      return data;
    },
  });
}

export function useCreateTrack() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: TrackInput): Promise<Track> => {
      const { data, error, response } = await api.POST("/api/tracks", { body });
      if (!data) fail(response, error, "Could not add the track.");
      return data;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: TRACKS_KEY }),
  });
}

export function useDeleteTrack() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number): Promise<void> => {
      const { error, response } = await api.DELETE("/api/tracks/{track_id}", {
        params: { path: { track_id: id } },
      });
      if (!response.ok) fail(response, error, "Could not remove the track.");
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: TRACKS_KEY }),
  });
}
