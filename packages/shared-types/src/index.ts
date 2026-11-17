/**
 * Nexora API contract (mirrors services/api/app/schemas), used by the web app.
 * Keep in sync with the FastAPI response models (see /docs on the API).
 */

export type UUID = string;
export type ISODate = string;

export interface ApiErrorBody {
  error: { code: string; message: string; request_id?: string | null; details?: unknown };
}

export interface Page<T> {
  items: T[];
  has_more: boolean;
  next_offset: number | null;
}

// ---- profile -----------------------------------------------------------------------------------

export type Language = "auto" | "en" | "ta";

export interface Profile {
  id: UUID;
  email: string | null;
  display_name: string | null;
  avatar_url: string | null;
  timezone: string;
  locale: string;
  onboarded_at: ISODate | null;
  created_at: ISODate;
}

export interface Preferences {
  preferred_language: Language;
  response_style: "concise" | "detailed";
  llm_mode: "auto" | "local" | "cloud";
  voice_name: string | null;
  voice_speaking_rate: number;
  wake_word_enabled: boolean;
  wake_word_sensitivity: number;
  wake_word_cooldown_seconds: number;
  push_to_talk_enabled: boolean;
  memory_enabled: boolean;
  memory_auto_extract: boolean;
  memory_retention_days: number | null;
  conversation_retention_days: number | null;
  store_voice_recordings: boolean;
  share_location: boolean;
  home_latitude: number | null;
  home_longitude: number | null;
  home_label: string | null;
  news_categories: string[];
  theme: "system" | "light" | "dark";
}

export interface Me {
  profile: Profile;
  preferences: Preferences;
}

export interface SystemStatus {
  environment: string;
  auth: { mode: "dev" | "supabase"; supabase: boolean };
  llm: {
    primary: string;
    model: string | null;
    primary_available: boolean;
    providers: string[];
    offline_fallback: boolean;
  };
  embeddings: { model: string };
  voice: { livekit: boolean; agent_name: string };
  vault: { configured: boolean; key_provider: string };
  integrations: Record<string, boolean>;
}

// ---- conversations & assistant ------------------------------------------------------------------

export interface Conversation {
  id: UUID;
  title: string;
  channel: "text" | "voice" | "automation";
  archived: boolean;
  last_message_at: ISODate;
  created_at: ISODate;
}

export interface ToolTrace {
  id: string;
  tool: string;
  status: string;
  message?: string;
  duration_ms?: number;
  approval_id?: string;
  reason?: string;
}

export interface MessageMeta {
  provider?: string;
  model?: string;
  offline?: boolean;
  cards?: ResultCard[];
  approvals?: ApprovalRequest[];
  approval_id?: string;
  approval_status?: string;
  error?: string;
  usage?: { input_tokens: number; output_tokens: number };
}

export interface Message {
  id: UUID;
  conversation_id: UUID;
  role: "user" | "assistant" | "system";
  content: string;
  status: "complete" | "error" | "cancelled";
  channel: string;
  run_id: string | null;
  tool_calls: ToolTrace[];
  meta: MessageMeta;
  created_at: ISODate;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
}

export interface ApprovalRequest {
  approval_id: UUID;
  tool: string;
  summary: string;
  expires_at: ISODate;
}

/** Rich result cards produced by tools (never sent to the LLM). */
export type ResultCard =
  | { type: "weather"; report: WeatherReport; tool?: string }
  | { type: "places"; category: string; label: string; center: GeoPoint; places: Place[]; attribution: string; tool?: string }
  | { type: "directions"; destination: GeocodeResult; url: string; tool?: string }
  | { type: "news"; items: NewsItem[]; tool?: string }
  | { type: "youtube"; items: YouTubeResult[]; tool?: string }
  | { type: "music"; provider: string; items: MusicResult[]; tool?: string }
  | { type: "emails"; items: EmailSummary[]; tool?: string }
  | { type: "email"; item: EmailSummary & { body_text?: string }; tool?: string }
  | { type: "email_draft"; draft: { draft_id: string; to: string; subject: string }; tool?: string }
  | { type: "email_sent"; to: string; subject: string; tool?: string }
  | { type: "whatsapp_sent"; to: string; tool?: string }
  | { type: "memory_saved"; memory: { id: UUID; content: string; kind: string }; tool?: string }
  | { type: "memories"; items: { id: UUID; content: string; kind: string }[]; tool?: string }
  | { type: "vault_items"; items: { id: UUID; name: string; kind: string; description: string | null }[]; tool?: string }
  | { type: "reminder"; id: UUID; message: string; when: string; tool?: string }
  | { type: "automation"; id: UUID; name: string; schedule: string; tool?: string }
  | { type: "briefing"; briefing: Briefing; tool?: string };

export type RunEvent =
  | { event: "run_started"; data: { run_id: string; conversation_id: UUID; user_message_id: UUID | null; created_conversation: boolean; channel: string } }
  | { event: "status"; data: { text: string } }
  | { event: "token"; data: { text: string } }
  | { event: "tool_start"; data: { id: string; tool: string; category: string } }
  | { event: "tool_end"; data: { id: string; tool: string; ok: boolean; message: string; duration_ms?: number; error_code?: string; card?: ResultCard } }
  | { event: "approval_required"; data: ApprovalRequest }
  | { event: "message_end"; data: { message_id: UUID; conversation_id: UUID; content: string; provider: string; model: string; offline: boolean; approvals: ApprovalRequest[]; cards: ResultCard[] } }
  | { event: "error"; data: { code: string; message: string; retryable?: boolean } }
  | { event: "cancelled"; data: { reason: string } }
  | { event: "done"; data: { status: string } };

// ---- discover ----------------------------------------------------------------------------------

export interface GeoPoint {
  latitude: number;
  longitude: number;
  label?: string | null;
}

export interface GeocodeResult {
  label: string;
  latitude: number;
  longitude: number;
  type: string | null;
}

export interface Place {
  id: string;
  name: string;
  category: string;
  latitude: number;
  longitude: number;
  distance_m: number | null;
  address: string | null;
  opening_hours: string | null;
  phone: string | null;
  website: string | null;
  brand: string | null;
  directions_url: string;
  osm_url: string;
}

export interface WeatherReport {
  latitude: number;
  longitude: number;
  timezone: string;
  location_label: string | null;
  attribution: string;
  current: {
    time: string;
    temperature_c: number;
    apparent_temperature_c: number | null;
    humidity_percent: number | null;
    precipitation_mm: number | null;
    wind_speed_kmh: number | null;
    weather_code: number;
    description: string;
    is_day: boolean;
  };
  daily: {
    date: string;
    weather_code: number;
    description: string;
    temperature_max_c: number | null;
    temperature_min_c: number | null;
    precipitation_probability_max: number | null;
    precipitation_sum_mm: number | null;
    wind_speed_max_kmh: number | null;
    sunrise: string | null;
    sunset: string | null;
  }[];
}

export interface NewsItem {
  id: string;
  title: string;
  link: string;
  source: string;
  category: string;
  published_at: ISODate | null;
  summary: string | null;
  image_url: string | null;
}

export interface YouTubeResult {
  id: string;
  kind: "video" | "channel" | "playlist";
  title: string;
  description: string | null;
  channel_title: string | null;
  published_at: string | null;
  thumbnail_url: string | null;
  url: string;
  embed_url: string | null;
}

export interface MusicResult {
  id: string;
  provider: string;
  kind: string;
  title: string;
  artist: string | null;
  album: string | null;
  artwork_url: string | null;
  url: string;
  embed_url: string | null;
  preview_url: string | null;
  duration_ms: number | null;
}

export interface EmailSummary {
  id: string;
  thread_id: string | null;
  from_: string | null;
  to: string | null;
  subject: string | null;
  date: string | null;
  snippet: string | null;
  unread: boolean;
  labels: string[];
}

export interface Briefing {
  generated_at: ISODate;
  timezone: string;
  text: string;
  mode: string;
  sections: {
    weather?: { location: string | null; now_c: number; conditions: string; min_c: number | null; max_c: number | null; rain_chance: number | null };
    news?: { title: string; source: string; link: string }[];
    email?: { unread_count: number; top: { from: string | null; subject: string | null }[] };
    reminders?: { message: string; at: string | null }[];
  };
  issues: string[];
}

// ---- memory & vault ----------------------------------------------------------------------------

export type MemoryKind = "profile" | "preference" | "fact" | "project" | "conversation_summary" | "note";

export interface Memory {
  id: UUID;
  kind: MemoryKind;
  content: string;
  source: string;
  importance: number;
  pinned: boolean;
  embedding_model: string | null;
  source_conversation_id: UUID | null;
  expires_at: ISODate | null;
  last_used_at: ISODate | null;
  created_at: ISODate;
  updated_at: ISODate;
  score: number | null;
}

export type VaultKind = "api_key" | "password" | "note" | "document" | "secret";

export interface VaultItem {
  id: UUID;
  name: string;
  kind: VaultKind;
  description: string | null;
  content_type: string | null;
  size_bytes: number;
  key_id: string;
  last_accessed_at: ISODate | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface VaultReveal {
  id: UUID;
  name: string;
  kind: VaultKind;
  secret: string | null;
  fields: Record<string, string> | null;
  file_base64: string | null;
  content_type: string | null;
}

export interface AuditLog {
  id: UUID;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  ip_address: string | null;
  details: Record<string, unknown>;
  created_at: ISODate;
}

// ---- automations, tasks, approvals, notifications -------------------------------------------------

export type AutomationKind = "morning_briefing" | "news_summary" | "email_summary" | "reminder" | "assistant_prompt";

export type Schedule =
  | { type: "once"; at: string }
  | { type: "daily"; time: string }
  | { type: "weekly"; time: string; days: number[] }
  | { type: "interval"; minutes: number };

export interface Automation {
  id: UUID;
  name: string;
  kind: AutomationKind;
  config: Record<string, unknown>;
  schedule: Schedule;
  timezone: string;
  enabled: boolean;
  next_run_at: ISODate | null;
  last_run_at: ISODate | null;
  last_status: string | null;
  consecutive_failures: number;
  max_retries: number;
  created_at: ISODate;
  schedule_description: string | null;
}

export interface TaskRun {
  id: UUID;
  automation_id: UUID | null;
  conversation_id: UUID | null;
  kind: string;
  title: string;
  status: "queued" | "running" | "retrying" | "succeeded" | "failed" | "cancelled" | "waiting_approval";
  scheduled_for: ISODate | null;
  started_at: ISODate | null;
  finished_at: ISODate | null;
  attempt: number;
  result: Record<string, unknown>;
  error: string | null;
  created_at: ISODate;
}

export interface Approval {
  id: UUID;
  conversation_id: UUID | null;
  tool_name: string;
  tool_args: Record<string, unknown>;
  summary: string;
  status: "pending" | "approved" | "rejected" | "expired" | "executed" | "failed";
  expires_at: ISODate;
  decided_at: ISODate | null;
  result: { ok?: boolean; message?: string };
  created_at: ISODate;
}

export interface Notification {
  id: UUID;
  kind: string;
  title: string;
  body: string;
  data: Record<string, unknown>;
  read_at: ISODate | null;
  created_at: ISODate;
}

export interface IntegrationStatus {
  provider: string;
  name: string;
  description: string;
  kind: "per_user" | "server";
  available: boolean;
  status: "connected" | "disconnected" | "error" | "not_configured" | "ready" | "pending";
  account_label: string | null;
  scopes: string[];
  connected_at: ISODate | null;
  last_error: string | null;
  setup_hint: string | null;
  tools: string[];
}

export interface ToolPermission {
  tool_name: string;
  category: string;
  description: string;
  risk: "read" | "write" | "sensitive";
  approval_policy: "never" | "always" | "configurable";
  integration: string | null;
  enabled: boolean;
  requires_approval: boolean;
}

export interface DashboardSummary {
  recent_conversations: Conversation[];
  pending_approvals: Approval[];
  pending_approval_count: number;
  recent_tasks: TaskRun[];
  unread_notifications: Notification[];
  unread_notification_count: number;
  upcoming_automations: { id: UUID; name: string; kind: AutomationKind; next_run_at: ISODate; schedule: string }[];
  latest_briefing: Briefing | null;
  connected_integrations: string[];
  memory_count: number;
}

// ---- voice -------------------------------------------------------------------------------------

export interface VoiceSession {
  session_id: UUID;
  room_name: string;
  server_url: string;
  participant_token: string;
  participant_identity: string;
  conversation_id: UUID;
  expires_at: ISODate;
}

export interface VoiceSessionSummary {
  id: UUID;
  room_name: string;
  status: string;
  activation: "push_to_talk" | "wake_word";
  language: string;
  conversation_id: UUID | null;
  started_at: ISODate | null;
  ended_at: ISODate | null;
  end_reason: string | null;
  turn_count: number;
  created_at: ISODate;
}

/** RPC methods and topics shared between the browser and services/voice-agent. */
export const VOICE_PROTOCOL = {
  rpcInterrupt: "nexora.interrupt",
  rpcStartTurn: "nexora.start_turn",
  rpcEndTurn: "nexora.end_turn",
  rpcCancelTurn: "nexora.cancel_turn",
  noticeTopic: "nexora.notice",
  toolTopic: "nexora.tool",
} as const;
