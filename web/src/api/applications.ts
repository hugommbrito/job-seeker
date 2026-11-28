import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/api/client";
import type { components, paths } from "@/api/schema";
import type { Filters } from "@/lib/filters";
import type { Outcome, Stage } from "@/lib/stages";

export type Application = components["schemas"]["ApplicationOut"];
export type ApplicationDetail = components["schemas"]["ApplicationDetailOut"];
export type ApplicationInput = components["schemas"]["ApplicationIn"];
export type ApplicationChanges = components["schemas"]["ApplicationPatch"];
export type TimelineEvent = components["schemas"]["EventOut"];
export type EventInput = components["schemas"]["EventIn"];

const LIST_KEY = ["applications"] as const;
const detailKey = (id: number) => ["application", id] as const;

/** Turn an error body into one readable sentence: a string detail, or field errors. */
export function errorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item: { loc?: unknown[]; msg?: string }) => {
          const field = item.loc?.slice(-1)[0];
          return field ? `${String(field).replaceAll("_", " ")}: ${item.msg}` : item.msg;
        })
        .join("; ");
    }
  }
  return fallback;
}

function fail(response: Response, error: unknown, fallback: string): never {
  throw new ApiError(response.status, errorMessage(error, fallback));
}

export function useApplications(filters?: Filters) {
  const query = filters
    ? { status: filters.status, stage: filters.stages, q: filters.q, sort: filters.sort }
    : {};
  return useQuery({
    queryKey: [...LIST_KEY, query],
    queryFn: async (): Promise<Application[]> => {
      const { data, error, response } = await api.GET("/api/applications", {
        params: { query },
      });
      if (!data) fail(response, error, "Could not load applications.");
      return data;
    },
  });
}

export function useApplication(id: number) {
  return useQuery({
    queryKey: detailKey(id),
    queryFn: async (): Promise<ApplicationDetail> => {
      const { data, error, response } = await api.GET("/api/applications/{application_id}", {
        params: { path: { application_id: id } },
      });
      if (!data) fail(response, error, "Could not load the application.");
      return data;
    },
  });
}

/** After any change, the card's detail is replaced and every list is refetched. */
function useSettle() {
  const queryClient = useQueryClient();
  return (detail?: ApplicationDetail) => {
    if (detail) queryClient.setQueryData(detailKey(detail.id), detail);
    void queryClient.invalidateQueries({ queryKey: LIST_KEY });
  };
}

export function useCreateApplication() {
  const settle = useSettle();
  return useMutation({
    mutationFn: async (body: ApplicationInput): Promise<ApplicationDetail> => {
      const { data, error, response } = await api.POST("/api/applications", { body });
      if (!data) fail(response, error, "Could not create the application.");
      return data;
    },
    onSuccess: settle,
  });
}

export function useUpdateApplication(id: number) {
  const settle = useSettle();
  return useMutation({
    mutationFn: async (body: ApplicationChanges): Promise<ApplicationDetail> => {
      const { data, error, response } = await api.PATCH("/api/applications/{application_id}", {
        params: { path: { application_id: id } },
        body,
      });
      if (!data) fail(response, error, "Could not save the changes.");
      return data;
    },
    onSuccess: settle,
  });
}

export function useDeleteApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number): Promise<void> => {
      const { error, response } = await api.DELETE("/api/applications/{application_id}", {
        params: { path: { application_id: id } },
      });
      if (!response.ok) fail(response, error, "Could not delete the application.");
    },
    onSuccess: (_result, id) => {
      queryClient.removeQueries({ queryKey: detailKey(id) });
      void queryClient.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}

/** Move, close or reopen: the three ways a card changes column. */
export type Transition =
  | { id: number; stage: Stage }
  | { id: number; outcome: Outcome }
  | { id: number; reopen: true };

export async function transition(change: Transition): Promise<ApplicationDetail> {
  const path = { application_id: change.id };
  const result =
    "stage" in change
      ? await api.POST("/api/applications/{application_id}/stage", {
          params: { path },
          body: { stage: change.stage },
        })
      : "outcome" in change
        ? await api.POST("/api/applications/{application_id}/close", {
            params: { path },
            body: { outcome: change.outcome },
          })
        : await api.POST("/api/applications/{application_id}/reopen", { params: { path } });
  if (!result.data) fail(result.response, result.error, "Could not move the application.");
  return result.data;
}

export function useTransition() {
  const queryClient = useQueryClient();
  const settle = useSettle();
  return useMutation({
    mutationFn: transition,
    // The card moves at once; the server's answer then replaces the guess.
    onMutate: async (change) => {
      await queryClient.cancelQueries({ queryKey: LIST_KEY });
      queryClient.setQueriesData<Application[]>({ queryKey: LIST_KEY }, (rows) =>
        rows?.map((row) => {
          if (row.id !== change.id) return row;
          if ("stage" in change) return { ...row, stage: change.stage };
          if ("outcome" in change) return { ...row, outcome: change.outcome };
          return { ...row, outcome: null };
        }),
      );
    },
    onSuccess: settle,
    onError: () => void queryClient.invalidateQueries({ queryKey: LIST_KEY }),
  });
}

export function useAddEvent(applicationId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: EventInput): Promise<TimelineEvent> => {
      const { data, error, response } = await api.POST(
        "/api/applications/{application_id}/events",
        { params: { path: { application_id: applicationId } }, body },
      );
      if (!data) fail(response, error, "Could not add to the timeline.");
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: detailKey(applicationId) });
      void queryClient.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}

export function useDeleteEvent(applicationId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (eventId: number): Promise<void> => {
      const { error, response } = await api.DELETE(
        "/api/applications/{application_id}/events/{event_id}",
        { params: { path: { application_id: applicationId, event_id: eventId } } },
      );
      if (!response.ok) fail(response, error, "Could not delete the entry.");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: detailKey(applicationId) });
      void queryClient.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}

export type Contact = components["schemas"]["ContactOut"];
export type ContactInput = components["schemas"]["ContactIn"];
export type StoredDocument = components["schemas"]["DocumentOut"];
export type DocumentKind = StoredDocument["kind"];
type UploadBody =
  paths["/api/applications/{application_id}/documents"]["post"]["requestBody"]["content"]["multipart/form-data"];

/** A plain link downloads it: the session cookie goes along, and the server forces a download. */
export function documentUrl(applicationId: number, documentId: number): string {
  return `/api/applications/${applicationId}/documents/${documentId}`;
}

function useRefresh(applicationId: number) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: detailKey(applicationId) });
  };
}

export function useAddContact(applicationId: number) {
  const refresh = useRefresh(applicationId);
  return useMutation({
    mutationFn: async (body: ContactInput): Promise<Contact> => {
      const { data, error, response } = await api.POST(
        "/api/applications/{application_id}/contacts",
        { params: { path: { application_id: applicationId } }, body },
      );
      if (!data) fail(response, error, "Could not add the contact.");
      return data;
    },
    onSuccess: refresh,
  });
}

export function useDeleteContact(applicationId: number) {
  const refresh = useRefresh(applicationId);
  return useMutation({
    mutationFn: async (contactId: number): Promise<void> => {
      const { error, response } = await api.DELETE(
        "/api/applications/{application_id}/contacts/{contact_id}",
        { params: { path: { application_id: applicationId, contact_id: contactId } } },
      );
      if (!response.ok) fail(response, error, "Could not remove the contact.");
    },
    onSuccess: refresh,
  });
}

export function useUploadDocument(applicationId: number) {
  const refresh = useRefresh(applicationId);
  return useMutation({
    mutationFn: async ({ file, kind }: { file: File; kind: DocumentKind }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      const { data, error, response } = await api.POST(
        "/api/applications/{application_id}/documents",
        {
          params: { path: { application_id: applicationId } },
          // The generated type describes the form's fields; the browser needs the form itself.
          body: form as unknown as UploadBody,
        },
      );
      if (!data) fail(response, error, "Could not upload the file.");
      return data;
    },
    onSuccess: refresh,
  });
}

export function useDeleteDocument(applicationId: number) {
  const refresh = useRefresh(applicationId);
  return useMutation({
    mutationFn: async (documentId: number): Promise<void> => {
      const { error, response } = await api.DELETE(
        "/api/applications/{application_id}/documents/{document_id}",
        { params: { path: { application_id: applicationId, document_id: documentId } } },
      );
      if (!response.ok) fail(response, error, "Could not delete the file.");
    },
    onSuccess: refresh,
  });
}
