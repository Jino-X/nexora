"use client";

import type { Preferences } from "@nexora/shared-types";
import {
  Bot,
  Database,
  Download,
  Ear,
  KeyRound,
  Loader2,
  LocateFixed,
  Settings,
  Shield,
  ShieldCheck,
  Trash2,
  User,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { ErrorState, PageHeader } from "@/components/common";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGeolocation } from "@/hooks/use-geolocation";
import { api } from "@/lib/api/client";
import {
  useMe,
  useSystemStatus,
  useToolPermissions,
  useUpdatePreferences,
  useUpdateProfile,
  useUpdateToolPermission,
  useUsage,
} from "@/lib/api/hooks";
import { useAuth } from "@/lib/auth/auth-provider";
import { getSupabase } from "@/lib/auth/supabase-browser";
import { wakeWordConfigured } from "@/lib/config";
import { useVoiceStore } from "@/lib/voice/voice-store";

function Row({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="max-w-md">
        <p className="text-sm font-medium">{label}</p>
        {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function usePref() {
  const update = useUpdatePreferences();
  return (patch: Partial<Preferences> & { clear_fields?: string[] }) =>
    update.mutate(patch, { onError: (e) => toast.error(e.message), onSuccess: () => toast.success("Saved") });
}

function ProfileTab() {
  const me = useMe();
  const update = useUpdateProfile();
  const setPref = usePref();
  const geo = useGeolocation();
  // Local edits override the loaded profile; null means "unchanged".
  const [nameEdit, setName] = useState<string | null>(null);
  const [timezoneEdit, setTimezone] = useState<string | null>(null);
  const name = nameEdit ?? me.data?.profile.display_name ?? "";
  const timezone = timezoneEdit ?? me.data?.profile.timezone ?? "UTC";
  const prefs = me.data?.preferences;

  // Save a freshly obtained device location as home (an external event -> server write).
  useEffect(() => {
    if (geo.coords)
      setPref({ home_latitude: geo.coords.latitude, home_longitude: geo.coords.longitude, home_label: "Home" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geo.coords]);

  // Browsers list canonical ICU names (Chromium has "Asia/Calcutta", not "Asia/Kolkata"), so make sure
  // the saved zone is always an option; otherwise the select renders blank.
  const supported = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  const zones = supported.includes(timezone) ? supported : [timezone, ...supported];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="display-name">Name</Label>
            <Input id="display-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Timezone</Label>
            <Select value={timezone} onValueChange={setTimezone}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="max-h-72">
                {zones.map((z) => (
                  <SelectItem key={z} value={z}>
                    {z}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <Button
          onClick={() =>
            update.mutate(
              { display_name: name, timezone },
              { onSuccess: () => toast.success("Profile saved"), onError: (e) => toast.error(e.message) },
            )
          }
          disabled={update.isPending}
        >
          {update.isPending && <Loader2 className="animate-spin" />} Save profile
        </Button>
        <div className="border-t pt-4">
          <Row
            label="Home location"
            hint={
              prefs?.home_latitude != null
                ? `${prefs.home_label ?? "Home"} (${prefs.home_latitude.toFixed(3)}, ${prefs.home_longitude?.toFixed(3)})`
                : "Used for weather and your morning briefing."
            }
          >
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={geo.request}>
                {geo.status === "locating" ? <Loader2 className="animate-spin" /> : <LocateFixed />} Set to current
                location
              </Button>
              {prefs?.home_latitude != null && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPref({ clear_fields: ["home_latitude", "home_longitude", "home_label"] })}
                >
                  Clear
                </Button>
              )}
            </div>
          </Row>
        </div>
      </CardContent>
    </Card>
  );
}

function AssistantTab() {
  const me = useMe();
  const status = useSystemStatus();
  const setPref = usePref();
  const prefs = me.data?.preferences;
  if (!prefs) return <Skeleton className="h-60" />;
  const llm = status.data?.llm;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Assistant</CardTitle>
        <CardDescription>
          Local model: <span className="text-foreground font-medium">{llm?.model ?? "…"}</span>{" "}
          {llm &&
            (llm.primary_available ? (
              <Badge variant="outline" className="text-success ml-1">
                reachable
              </Badge>
            ) : (
              <Badge variant="outline" className="text-warning ml-1">
                not reachable, using fallback
              </Badge>
            ))}
        </CardDescription>
      </CardHeader>
      <CardContent className="divide-y">
        <Row
          label="Model preference"
          hint="Local keeps everything on your own server. Cloud uses the configured fallback provider first, if one exists."
        >
          <Select value={prefs.llm_mode} onValueChange={(v) => setPref({ llm_mode: v as Preferences["llm_mode"] })}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">Automatic</SelectItem>
              <SelectItem value="local">Local only</SelectItem>
              <SelectItem value="cloud" disabled={!llm?.providers.includes("openai_compatible")}>
                Cloud first
              </SelectItem>
            </SelectContent>
          </Select>
        </Row>
        <Row label="Response language" hint="Automatic matches the language you use, including Tamil-English mix.">
          <Select
            value={prefs.preferred_language}
            onValueChange={(v) => setPref({ preferred_language: v as Preferences["preferred_language"] })}
          >
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">Automatic</SelectItem>
              <SelectItem value="en">English</SelectItem>
              <SelectItem value="ta">தமிழ் Tamil</SelectItem>
            </SelectContent>
          </Select>
        </Row>
        <Row label="Response style">
          <Select
            value={prefs.response_style}
            onValueChange={(v) => setPref({ response_style: v as Preferences["response_style"] })}
          >
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="concise">Concise</SelectItem>
              <SelectItem value="detailed">Detailed</SelectItem>
            </SelectContent>
          </Select>
        </Row>
        <Row label="News categories" hint="Used for headlines and briefings.">
          <div className="flex max-w-sm flex-wrap justify-end gap-1.5">
            {["world", "india", "technology", "ai", "business", "science"].map((c) => {
              const on = prefs.news_categories.includes(c);
              return (
                <button
                  key={c}
                  type="button"
                  onClick={() =>
                    setPref({
                      news_categories: on
                        ? prefs.news_categories.filter((x) => x !== c)
                        : [...prefs.news_categories, c],
                    })
                  }
                  className={`rounded-full border px-2.5 py-1 text-xs capitalize ${on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted"}`}
                >
                  {c === "ai" ? "AI" : c}
                </button>
              );
            })}
          </div>
        </Row>
      </CardContent>
    </Card>
  );
}

function VoiceTab() {
  const me = useMe();
  const status = useSystemStatus();
  const setPref = usePref();
  const prefs = me.data?.preferences;
  const [sensitivityDraft, setSensitivity] = useState<number | null>(null);
  const wakeWordState = useVoiceStore((s) => s.wakeWord);
  const wakeWordError = useVoiceStore((s) => s.wakeWordError);
  if (!prefs) return <Skeleton className="h-60" />;
  const sensitivity = sensitivityDraft ?? prefs.wake_word_sensitivity;
  return (
    <div className="space-y-4">
      {status.data && !status.data.voice.livekit && (
        <Alert>
          <Ear />
          <AlertTitle>Voice isn&apos;t configured on this server</AlertTitle>
          <AlertDescription>
            An administrator needs to set the LiveKit URL, API key and secret, and run the voice agent (docs/voice.md).
          </AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Voice conversations</CardTitle>
        </CardHeader>
        <CardContent className="divide-y">
          <Row
            label="Hold to talk"
            hint="Off: hands-free with automatic turn detection. On: hold the button while speaking."
          >
            <Switch
              checked={prefs.push_to_talk_enabled}
              onCheckedChange={(v) => setPref({ push_to_talk_enabled: v })}
            />
          </Row>
          <Row label="Speaking rate">
            <div className="flex w-56 items-center gap-3">
              <Slider
                min={0.7}
                max={1.4}
                step={0.05}
                defaultValue={[prefs.voice_speaking_rate]}
                onValueCommit={([v]) => setPref({ voice_speaking_rate: v })}
              />
              <span className="w-10 text-right text-sm tabular-nums">{prefs.voice_speaking_rate.toFixed(2)}×</span>
            </div>
          </Row>
          <Row
            label="Voice"
            hint="Speaker description for the TTS engine (for example 'Jaya' or 'Thoma' for Indic Parler-TTS)."
          >
            <Input
              className="w-56"
              defaultValue={prefs.voice_name ?? ""}
              placeholder="Default"
              onBlur={(e) =>
                e.target.value !== (prefs.voice_name ?? "") &&
                setPref(e.target.value ? { voice_name: e.target.value } : { clear_fields: ["voice_name"] })
              }
            />
          </Row>
          <Row
            label="Store voice recordings"
            hint="Off by default. Nexora keeps transcripts only, never raw audio, unless you turn this on."
          >
            <Switch
              checked={prefs.store_voice_recordings}
              onCheckedChange={(v) => setPref({ store_voice_recordings: v })}
            />
          </Row>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Wake word: “Hey Nexora”</CardTitle>
          <CardDescription>
            Detection runs on this device. No audio leaves your browser until the wake word is heard. It works only
            while Nexora is open in the foreground. Phones and browsers pause the microphone in background tabs.
          </CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          {(!wakeWordConfigured || wakeWordState === "unconfigured") && (
            <p className="text-warning pb-3 text-sm">
              {!wakeWordConfigured
                ? "The wake word is turned off on this deployment."
                : `The wake word model isn't installed yet. ${wakeWordError ?? ""}`}{" "}
              Tapping the mic still works.
            </p>
          )}
          <Row label="Enable wake word">
            <Switch checked={prefs.wake_word_enabled} onCheckedChange={(v) => setPref({ wake_word_enabled: v })} />
          </Row>
          <Row label="Sensitivity" hint="Higher catches more, but triggers falsely more often.">
            <div className="flex w-56 items-center gap-3">
              <Slider
                min={0.1}
                max={0.95}
                step={0.05}
                value={[sensitivity]}
                onValueChange={([v]) => setSensitivity(v)}
                onValueCommit={([v]) => setPref({ wake_word_sensitivity: v })}
              />
              <span className="w-10 text-right text-sm tabular-nums">{sensitivity.toFixed(2)}</span>
            </div>
          </Row>
          <Row label="Cooldown" hint="Ignore detections for this long after a session starts.">
            <Select
              value={String(prefs.wake_word_cooldown_seconds)}
              onValueChange={(v) => setPref({ wake_word_cooldown_seconds: Number(v) })}
            >
              <SelectTrigger className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[2, 4, 8, 15, 30].map((s) => (
                  <SelectItem key={s} value={String(s)}>
                    {s}s
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
        </CardContent>
      </Card>
    </div>
  );
}

function PrivacyTab() {
  const me = useMe();
  const setPref = usePref();
  const prefs = me.data?.preferences;
  if (!prefs) return <Skeleton className="h-60" />;
  const retention = (value: number | null, field: "memory_retention_days" | "conversation_retention_days") => (
    <Select
      value={value ? String(value) : "forever"}
      onValueChange={(v) => setPref(v === "forever" ? { clear_fields: [field] } : { [field]: Number(v) })}
    >
      <SelectTrigger className="w-36">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="forever">Keep</SelectItem>
        {[7, 30, 90, 365].map((d) => (
          <SelectItem key={d} value={String(d)}>
            {d} days
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Privacy</CardTitle>
      </CardHeader>
      <CardContent className="divide-y">
        <Row label="Personal memory" hint="Allow Nexora to read and save memories you ask it to keep.">
          <Switch checked={prefs.memory_enabled} onCheckedChange={(v) => setPref({ memory_enabled: v })} />
        </Row>
        <Row label="Memory retention" hint="New memories expire after this period.">
          {retention(prefs.memory_retention_days, "memory_retention_days")}
        </Row>
        <Row label="Conversation retention" hint="Older conversations are deleted automatically.">
          {retention(prefs.conversation_retention_days, "conversation_retention_days")}
        </Row>
        <Row
          label="Share location with the assistant"
          hint="When off, Nexora ignores device location even if your browser shares it."
        >
          <Switch checked={prefs.share_location} onCheckedChange={(v) => setPref({ share_location: v })} />
        </Row>
      </CardContent>
    </Card>
  );
}

function PermissionsTab() {
  const perms = useToolPermissions();
  const update = useUpdateToolPermission();
  if (perms.isPending) return <Skeleton className="h-80" />;
  if (perms.error) return <ErrorState error={perms.error} />;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Assistant permissions</CardTitle>
        <CardDescription>
          Choose which tools Nexora may use. Sending messages always asks for your approval.
        </CardDescription>
      </CardHeader>
      <CardContent className="divide-y">
        {perms.data?.map((p) => (
          <div key={p.tool_name} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                <span className="font-mono text-xs">{p.tool_name}</span>
                <Badge variant="outline" className="capitalize">
                  {p.risk}
                </Badge>
                {p.integration && <Badge variant="secondary">{p.integration}</Badge>}
              </p>
              <p className="text-muted-foreground text-xs">{p.description}</p>
            </div>
            <div className="flex items-center gap-4 text-xs">
              {p.approval_policy !== "never" && (
                <label className="flex items-center gap-2">
                  Ask first
                  <Switch
                    checked={p.requires_approval}
                    disabled={p.approval_policy === "always"}
                    onCheckedChange={(v) => update.mutate({ tool: p.tool_name, requires_approval: v })}
                  />
                </label>
              )}
              <label className="flex items-center gap-2">
                Allowed
                <Switch checked={p.enabled} onCheckedChange={(v) => update.mutate({ tool: p.tool_name, enabled: v })} />
              </label>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function SecurityTab() {
  const auth = useAuth();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  async function changePassword() {
    setBusy(true);
    const { error } = await getSupabase().auth.updateUser({ password });
    setBusy(false);
    if (error) toast.error(error.message);
    else {
      toast.success("Password updated");
      setPassword("");
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Security</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {auth.mode === "dev" ? (
          <Alert>
            <Shield />
            <AlertTitle>Development authentication</AlertTitle>
            <AlertDescription>
              This server uses the dev login. Configure Supabase Auth for real accounts, passwords and email
              verification.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="flex max-w-md gap-2">
            <Input
              type="password"
              autoComplete="new-password"
              placeholder="New password (min 8 characters)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button onClick={changePassword} disabled={busy || password.length < 8}>
              {busy && <Loader2 className="animate-spin" />} Update
            </Button>
          </div>
        )}
        <ul className="text-muted-foreground space-y-2 text-sm">
          <li className="flex gap-2">
            <ShieldCheck className="text-success size-4 shrink-0" /> Every API request is verified against your Supabase
            session, and each user&apos;s data is isolated.
          </li>
          <li className="flex gap-2">
            <KeyRound className="text-success size-4 shrink-0" /> Integration tokens and vault items use envelope
            encryption with per-item keys.
          </li>
          <li className="flex gap-2">
            <Ear className="text-success size-4 shrink-0" /> Voice tokens last 10 minutes and are scoped to one private
            room.
          </li>
        </ul>
        <Button variant="outline" onClick={() => void auth.signOut()}>
          Sign out
        </Button>
      </CardContent>
    </Card>
  );
}

function DataTab() {
  const auth = useAuth();
  const router = useRouter();
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const usage = useUsage();

  async function exportData() {
    const data = await api<unknown>("/me/export", { timeoutMs: 60_000 });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    a.download = `nexora-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function deleteAccount() {
    setBusy(true);
    try {
      await api("/me", { method: "DELETE", body: { confirm } });
      toast.success("Your account was deleted");
      await auth.signOut();
      router.replace("/signup");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Deletion failed");
    } finally {
      setBusy(false);
    }
  }

  const totals = usage.data?.rows.reduce(
    (acc, r) => ({ calls: acc.calls + r.calls, tokens: acc.tokens + r.input_tokens + r.output_tokens }),
    { calls: 0, tokens: 0 },
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Usage (30 days)</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-3">
          <div className="rounded-xl border p-3">
            <p className="text-muted-foreground text-xs">Model + tool calls</p>
            <p className="text-xl font-semibold tabular-nums">{totals?.calls ?? "-"}</p>
          </div>
          <div className="rounded-xl border p-3">
            <p className="text-muted-foreground text-xs">Tokens</p>
            <p className="text-xl font-semibold tabular-nums">{totals?.tokens.toLocaleString() ?? "-"}</p>
          </div>
          <div className="rounded-xl border p-3">
            <p className="text-muted-foreground text-xs">Providers</p>
            <p className="truncate text-sm font-medium">
              {[...new Set(usage.data?.rows.map((r) => r.provider).filter(Boolean))].join(", ") || "-"}
            </p>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Your data</CardTitle>
          <CardDescription>
            Download everything Nexora stores about you as JSON. Vault secrets and tokens are excluded.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={exportData}>
            <Download /> Export my data
          </Button>
        </CardContent>
      </Card>
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-destructive">Delete account</CardTitle>
          <CardDescription>
            Permanently deletes your profile, conversations, memories, vault, automations and connections, and revokes
            Gmail access.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex max-w-md gap-2">
          <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder='Type "DELETE" to confirm' />
          <Button variant="destructive" disabled={confirm !== "DELETE" || busy} onClick={deleteAccount}>
            {busy ? <Loader2 className="animate-spin" /> : <Trash2 />} Delete
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

const TABS = [
  { id: "profile", label: "Profile", icon: User, el: <ProfileTab /> },
  { id: "assistant", label: "Assistant", icon: Bot, el: <AssistantTab /> },
  { id: "voice", label: "Voice", icon: Ear, el: <VoiceTab /> },
  { id: "privacy", label: "Privacy", icon: Shield, el: <PrivacyTab /> },
  { id: "permissions", label: "Permissions", icon: ShieldCheck, el: <PermissionsTab /> },
  { id: "security", label: "Security", icon: KeyRound, el: <SecurityTab /> },
  { id: "data", label: "Data", icon: Database, el: <DataTab /> },
];

function SettingsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = TABS.some((t) => t.id === params.get("tab")) ? (params.get("tab") as string) : "profile";
  return (
    <div>
      <PageHeader
        tone="sky"
        title="Settings"
        icon={Settings}
        description="Profile, assistant behaviour, voice and wake word, privacy, permissions and your data."
      />
      <Tabs value={tab} onValueChange={(v) => router.replace(`/settings?tab=${v}`, { scroll: false })}>
        <TabsList className="mb-4 w-full scrollbar-thin justify-start overflow-x-auto">
          {TABS.map((t) => (
            <TabsTrigger key={t.id} value={t.id} className="gap-1.5">
              <t.icon className="size-3.5" />
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map((t) => (
          <TabsContent key={t.id} value={t.id}>
            {t.el}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense>
      <SettingsInner />
    </Suspense>
  );
}
