"use client";

import type {
  Approval,
  Automation,
  AutomationKind,
  Conversation,
  ConversationDetail,
  DashboardSummary,
  GeocodeResult,
  IntegrationStatus,
  Me,
  Memory,
  MemoryKind,
  MusicResult,
  NewsItem,
  Notification,
  Page,
  Place,
  Preferences,
  Profile,
  Schedule,
  SystemStatus,
  TaskRun,
  ToolPermission,
  VaultItem,
  VaultKind,
  VaultReveal,
  AuditLog,
  VoiceSessionSummary,
  WeatherReport,
  YouTubeResult,
} from "@nexora/shared-types";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-provider";

export const qk = {
  status: ["system-status"] as const,
  me: ["me"] as const,
  dashboard: ["dashboard"] as const,
  conversations: (q?: string) => ["conversations", q ?? ""] as const,
  conversation: (id: string) => ["conversation", id] as const,
  memories: (q: string, kind: string) => ["memories", q, kind] as const,
  vault: ["vault"] as const,
  vaultAudit: ["vault-audit"] as const,
  automations: ["automations"] as const,
  automationRuns: (id: string) => ["automation-runs", id] as const,
  tasks: (status?: string) => ["tasks", status ?? ""] as const,
  approvals: (status?: string) => ["approvals", status ?? ""] as const,
  notifications: (unread: boolean) => ["notifications", unread] as const,
  unreadCount: ["notifications-unread"] as const,
  integrations: ["integrations"] as const,
  permissions: ["tool-permissions"] as const,
  voiceSessions: ["voice-sessions"] as const,
  usage: ["usage"] as const,
};

function useAuthed() {
  return useAuth().status === "authenticated";
}

// ---- system & profile --------------------------------------------------------------------------

export function useSystemStatus() {
  return useQuery({ queryKey: qk.status, queryFn: () => api<SystemStatus>("/system/status"), staleTime: 60_000 });
}

export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: () => api<Me>("/me"), enabled: useAuthed(), staleTime: 60_000 });
}

export function useUpdatePreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Preferences> & { clear_fields?: string[] }) =>
      api<Preferences>("/me/preferences", { method: "PATCH", body }),
    onSuccess: (prefs) => qc.setQueryData<Me>(qk.me, (old) => (old ? { ...old, preferences: prefs } : old)),
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Pick<Profile, "display_name" | "timezone" | "locale" | "avatar_url">>) =>
      api<Profile>("/me/profile", { method: "PATCH", body }),
    onSuccess: (profile) => qc.setQueryData<Me>(qk.me, (old) => (old ? { ...old, profile } : old)),
  });
}

export function useOnboarding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      display_name: string;
      timezone: string;
      preferred_language: string;
      news_categories: string[];
      memory_enabled: boolean;
      home_label?: string | null;
      home_latitude?: number | null;
      home_longitude?: number | null;
    }) => api<Me>("/me/onboarding", { method: "POST", body }),
    onSuccess: (me) => qc.setQueryData(qk.me, me),
  });
}

export function useUsage() {
  return useQuery({
    queryKey: qk.usage,
    queryFn: () =>
      api<{
        rows: {
          day: string;
          event_type: string;
          provider: string | null;
          calls: number;
          input_tokens: number;
          output_tokens: number;
          avg_ms: number;
        }[];
      }>("/me/usage"),
    enabled: useAuthed(),
  });
}

export function useDashboard() {
  return useQuery({
    queryKey: qk.dashboard,
    queryFn: () => api<DashboardSummary>("/dashboard"),
    enabled: useAuthed(),
    refetchInterval: 60_000,
  });
}

// ---- conversations -----------------------------------------------------------------------------

export function useConversations(q?: string, limit = 30) {
  return useQuery({
    queryKey: qk.conversations(q),
    queryFn: () => api<Page<Conversation>>("/conversations", { query: { q, limit } }),
    enabled: useAuthed(),
    placeholderData: keepPreviousData,
  });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: qk.conversation(id ?? ""),
    queryFn: () => api<ConversationDetail>(`/conversations/${id}`),
    enabled: useAuthed() && Boolean(id),
  });
}

export function useUpdateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; title?: string; archived?: boolean }) =>
      api<Conversation>(`/conversations/${id}`, { method: "PATCH", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

// ---- discover ----------------------------------------------------------------------------------

export function useWeather(lat?: number | null, lon?: number | null, enabled = true) {
  return useQuery({
    queryKey: ["weather", lat ?? "home", lon ?? "home"],
    queryFn: () => api<WeatherReport>("/weather", { query: { lat, lon } }),
    enabled: useAuthed() && enabled,
    staleTime: 10 * 60_000,
    retry: false,
  });
}

export function useNews(category?: string, q?: string, limit = 30) {
  return useQuery({
    queryKey: ["news", category ?? "", q ?? "", limit],
    queryFn: () => api<NewsItem[]>("/news", { query: { category, q, limit } }),
    enabled: useAuthed(),
    staleTime: 10 * 60_000,
  });
}

export function useNearby(category: string, lat?: number, lon?: number, radius = 3000) {
  return useQuery({
    queryKey: ["nearby", category, lat, lon, radius],
    queryFn: () =>
      api<Place[]>("/location/nearby", { query: { category, lat, lon, radius_m: radius }, timeoutMs: 60_000 }),
    enabled: useAuthed() && lat !== undefined && lon !== undefined,
    staleTime: 10 * 60_000,
    retry: false,
  });
}

export function useGeocode() {
  return useMutation({
    mutationFn: (q: string) => api<GeocodeResult[]>("/location/geocode", { query: { q } }),
  });
}

export function useYouTubeSearch(q: string, kind: string) {
  return useQuery({
    queryKey: ["youtube", q, kind],
    queryFn: () => api<YouTubeResult[]>("/youtube/search", { query: { q, kind } }),
    enabled: useAuthed() && q.length > 0,
    staleTime: 60 * 60_000,
    retry: false,
  });
}

export function useMusicSearch(q: string) {
  return useQuery({
    queryKey: ["music", q],
    queryFn: () => api<MusicResult[]>("/music/search", { query: { q } }),
    enabled: useAuthed() && q.length > 0,
    staleTime: 60 * 60_000,
  });
}

// ---- memory ------------------------------------------------------------------------------------

export function useMemories(q: string, kind: string) {
  return useQuery({
    queryKey: qk.memories(q, kind),
    queryFn: () => api<Page<Memory>>("/memories", { query: { q, kind, limit: 100 } }),
    enabled: useAuthed(),
    placeholderData: keepPreviousData,
  });
}

export function useMemoryMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["memories"] });
  return {
    create: useMutation({
      mutationFn: (body: { content: string; kind: MemoryKind; pinned?: boolean }) =>
        api<Memory>("/memories", { method: "POST", body }),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, ...body }: { id: string; content?: string; kind?: MemoryKind; pinned?: boolean }) =>
        api<Memory>(`/memories/${id}`, { method: "PATCH", body }),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api(`/memories/${id}`, { method: "DELETE" }),
      onSuccess: invalidate,
    }),
    removeAll: useMutation({
      mutationFn: () => api("/memories", { method: "DELETE", query: { confirm: true } }),
      onSuccess: invalidate,
    }),
    reindex: useMutation({
      mutationFn: () => api<{ reindexed: number }>("/memories/reindex", { method: "POST" }),
      onSuccess: invalidate,
    }),
  };
}

// ---- vault -------------------------------------------------------------------------------------

export function useVaultStatus() {
  return useQuery({
    queryKey: ["vault-status"],
    queryFn: () => api<{ configured: boolean; key_provider: string; reauth_minutes: number }>("/vault/status"),
    enabled: useAuthed(),
  });
}

export function useVault() {
  return useQuery({ queryKey: qk.vault, queryFn: () => api<VaultItem[]>("/vault"), enabled: useAuthed() });
}

export function useVaultAudit() {
  return useQuery({
    queryKey: qk.vaultAudit,
    queryFn: () => api<Page<AuditLog>>("/vault/audit", { query: { limit: 50 } }),
    enabled: useAuthed(),
  });
}

export function useVaultMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: qk.vault });
    qc.invalidateQueries({ queryKey: qk.vaultAudit });
  };
  return {
    create: useMutation({
      mutationFn: (body: {
        name: string;
        kind: VaultKind;
        description?: string;
        secret?: string;
        fields?: Record<string, string>;
        file_base64?: string;
        content_type?: string;
      }) => api<VaultItem>("/vault", { method: "POST", body }),
      onSuccess: invalidate,
    }),
    reveal: useMutation({
      mutationFn: (id: string) => api<VaultReveal>(`/vault/${id}/reveal`, { method: "POST" }),
      onSuccess: () => qc.invalidateQueries({ queryKey: qk.vaultAudit }),
    }),
    remove: useMutation({
      mutationFn: (id: string) => api(`/vault/${id}`, { method: "DELETE" }),
      onSuccess: invalidate,
    }),
  };
}

// ---- automations, tasks, approvals, notifications -------------------------------------------------

export function useAutomations() {
  return useQuery({ queryKey: qk.automations, queryFn: () => api<Automation[]>("/automations"), enabled: useAuthed() });
}

export function useAutomationRuns(id: string | null) {
  return useQuery({
    queryKey: qk.automationRuns(id ?? ""),
    queryFn: () => api<Page<TaskRun>>(`/automations/${id}/runs`),
    enabled: useAuthed() && Boolean(id),
  });
}

export function useAutomationMutations() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: qk.automations });
    qc.invalidateQueries({ queryKey: qk.dashboard });
  };
  return {
    create: useMutation({
      mutationFn: (body: {
        name: string;
        kind: AutomationKind;
        schedule: Schedule;
        timezone?: string;
        config: Record<string, unknown>;
      }) => api<Automation>("/automations", { method: "POST", body }),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, ...body }: { id: string; enabled?: boolean; name?: string; schedule?: Schedule }) =>
        api<Automation>(`/automations/${id}`, { method: "PATCH", body }),
      onSuccess: invalidate,
    }),
    runNow: useMutation({
      mutationFn: (id: string) => api<Automation>(`/automations/${id}/run`, { method: "POST" }),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api(`/automations/${id}`, { method: "DELETE" }),
      onSuccess: invalidate,
    }),
  };
}

export function useSchedulePreview(schedule: Schedule | null, timezone: string) {
  return useQuery({
    queryKey: ["schedule-preview", schedule, timezone],
    queryFn: () =>
      api<{ description: string; next_runs: string[] }>("/automations/preview", {
        method: "POST",
        body: { schedule, timezone },
      }),
    enabled: useAuthed() && schedule !== null,
    retry: false,
  });
}

export function useTasks(status?: string) {
  return useQuery({
    queryKey: qk.tasks(status),
    queryFn: () => api<Page<TaskRun>>("/tasks", { query: { status, limit: 50 } }),
    enabled: useAuthed(),
    refetchInterval: 30_000,
  });
}

export function useApprovals(status?: string) {
  return useQuery({
    queryKey: qk.approvals(status),
    queryFn: () => api<Page<Approval>>("/approvals", { query: { status, limit: 50 } }),
    enabled: useAuthed(),
    refetchInterval: 30_000,
  });
}

export function useApprovalDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      api<Approval>(`/approvals/${id}/${approve ? "approve" : "reject"}`, { method: "POST", timeoutMs: 60_000 }),
    onSuccess: (approval) => {
      qc.invalidateQueries({ queryKey: ["approvals"] });
      qc.invalidateQueries({ queryKey: qk.dashboard });
      qc.invalidateQueries({ queryKey: ["tasks"] });
      if (approval.conversation_id) qc.invalidateQueries({ queryKey: qk.conversation(approval.conversation_id) });
    },
  });
}

export function useNotifications(unread = false) {
  return useQuery({
    queryKey: qk.notifications(unread),
    queryFn: () => api<Page<Notification>>("/notifications", { query: { unread, limit: 50 } }),
    enabled: useAuthed(),
    refetchInterval: 45_000,
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: qk.unreadCount,
    queryFn: () => api<{ count: number }>("/notifications/unread-count"),
    enabled: useAuthed(),
    refetchInterval: 30_000,
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids?: string[]) => api("/notifications/read", { method: "POST", body: { ids: ids ?? null } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
      qc.invalidateQueries({ queryKey: qk.unreadCount });
      qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });
}

// ---- integrations & permissions ------------------------------------------------------------------

export function useIntegrations() {
  return useQuery({
    queryKey: qk.integrations,
    queryFn: () => api<IntegrationStatus[]>("/integrations"),
    enabled: useAuthed(),
  });
}

export function useIntegrationMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: qk.integrations });
  return {
    connectGmail: useMutation({
      mutationFn: () => api<{ authorization_url: string }>("/integrations/gmail/connect", { method: "POST" }),
    }),
    configureWhatsApp: useMutation({
      mutationFn: (body: {
        phone_number_id: string;
        access_token: string;
        business_account_id?: string;
        display_phone_number?: string;
      }) => api<IntegrationStatus>("/integrations/whatsapp", { method: "PUT", body }),
      onSuccess: invalidate,
    }),
    disconnect: useMutation({
      mutationFn: (provider: string) => api(`/integrations/${provider}/disconnect`, { method: "POST" }),
      onSuccess: invalidate,
    }),
  };
}

export function useToolPermissions() {
  return useQuery({
    queryKey: qk.permissions,
    queryFn: () => api<ToolPermission[]>("/permissions/tools"),
    enabled: useAuthed(),
  });
}

export function useUpdateToolPermission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ tool, ...body }: { tool: string; enabled?: boolean; requires_approval?: boolean }) =>
      api<ToolPermission>(`/permissions/tools/${tool}`, { method: "PUT", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.permissions }),
  });
}

export function useVoiceSessions() {
  return useQuery({
    queryKey: qk.voiceSessions,
    queryFn: () => api<Page<VoiceSessionSummary>>("/voice/sessions"),
    enabled: useAuthed(),
  });
}
