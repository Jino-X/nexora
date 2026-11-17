"use client";

import type { Automation, AutomationKind, Schedule } from "@nexora/shared-types";
import {
  Bell,
  Bot,
  CalendarClock,
  ChevronDown,
  Loader2,
  Mail,
  Newspaper,
  Play,
  Plus,
  Sunrise,
  Trash2,
  Workflow,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, IconTile, PageHeader, StatusBadge, type Tone } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useAutomationMutations, useAutomationRuns, useAutomations, useMe, useSchedulePreview } from "@/lib/api/hooks";
import { formatDateTime, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const KINDS: Record<AutomationKind, { label: string; icon: typeof Bell; description: string }> = {
  morning_briefing: {
    label: "Morning briefing",
    icon: Sunrise,
    description: "Weather, headlines, unread email and today's reminders.",
  },
  news_summary: { label: "News summary", icon: Newspaper, description: "A short digest of your news categories." },
  email_summary: { label: "Email summary", icon: Mail, description: "Summary of unread Gmail messages (needs Gmail)." },
  reminder: { label: "Reminder", icon: Bell, description: "A notification at the time you choose." },
  assistant_prompt: {
    label: "Scheduled assistant task",
    icon: Bot,
    description: "Run any prompt on a schedule. Sensitive actions still need your approval.",
  },
};

const KIND_TONES: Record<AutomationKind, Tone> = {
  morning_briefing: "amber",
  news_summary: "sky",
  email_summary: "rose",
  reminder: "pink",
  assistant_prompt: "violet",
};

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function localDateTimeDefault() {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  d.setMinutes(0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function CreateDialog({
  open,
  onOpenChange,
  initialKind,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  initialKind?: AutomationKind;
}) {
  const me = useMe();
  const { create } = useAutomationMutations();
  const timezone = me.data?.profile.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
  const [kind, setKind] = useState<AutomationKind>(initialKind ?? "morning_briefing");
  const [name, setName] = useState("");
  const [type, setType] = useState<Schedule["type"]>(initialKind === "reminder" ? "once" : "daily");
  const [time, setTime] = useState("07:30");
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [at, setAt] = useState(localDateTimeDefault);
  const [minutes, setMinutes] = useState(60);
  const [message, setMessage] = useState("");
  const [prompt, setPrompt] = useState("");

  const schedule = useMemo<Schedule | null>(() => {
    if (type === "once") return at ? { type, at } : null;
    if (type === "daily") return { type, time };
    if (type === "weekly") return days.length ? { type, time, days } : null;
    return { type, minutes };
  }, [type, at, time, days, minutes]);
  const preview = useSchedulePreview(schedule, timezone);

  async function save() {
    if (!schedule) return;
    const config: Record<string, unknown> =
      kind === "reminder" ? { message } : kind === "assistant_prompt" ? { prompt } : {};
    try {
      await create.mutateAsync({ name: name || KINDS[kind].label, kind, schedule, timezone, config });
      toast.success("Automation created");
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't create");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New automation</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-2">
            {(Object.keys(KINDS) as AutomationKind[]).map((k) => {
              const meta = KINDS[k];
              return (
                <button
                  key={k}
                  type="button"
                  onClick={() => {
                    setKind(k);
                    if (k === "reminder") setType("once");
                  }}
                  className={cn(
                    "flex items-start gap-3 rounded-xl border p-3 text-left text-sm",
                    kind === k ? "border-brand bg-brand-soft" : "hover:bg-muted",
                  )}
                >
                  <meta.icon className="text-brand mt-0.5 size-4 shrink-0" />
                  <span>
                    <span className="block font-medium">{meta.label}</span>
                    <span className="text-muted-foreground text-xs">{meta.description}</span>
                  </span>
                </button>
              );
            })}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="auto-name">Name</Label>
            <Input
              id="auto-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={KINDS[kind].label}
            />
          </div>
          {kind === "reminder" && (
            <div className="space-y-1.5">
              <Label htmlFor="auto-message">Remind me to…</Label>
              <Input
                id="auto-message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Call the client"
              />
            </div>
          )}
          {kind === "assistant_prompt" && (
            <div className="space-y-1.5">
              <Label htmlFor="auto-prompt">Prompt</Label>
              <Textarea
                id="auto-prompt"
                rows={3}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Check tomorrow's weather in Chennai and tell me if I need an umbrella"
              />
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Repeat</Label>
              <Select value={type} onValueChange={(v) => setType(v as Schedule["type"])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="once">Once</SelectItem>
                  <SelectItem value="daily">Every day</SelectItem>
                  <SelectItem value="weekly">On certain days</SelectItem>
                  <SelectItem value="interval">Every N minutes</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {type === "once" ? (
              <div className="space-y-1.5">
                <Label htmlFor="auto-at">Date & time</Label>
                <Input id="auto-at" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
              </div>
            ) : type === "interval" ? (
              <div className="space-y-1.5">
                <Label htmlFor="auto-min">Minutes</Label>
                <Input
                  id="auto-min"
                  type="number"
                  min={5}
                  value={minutes}
                  onChange={(e) => setMinutes(Number(e.target.value))}
                />
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label htmlFor="auto-time">Time</Label>
                <Input id="auto-time" type="time" value={time} onChange={(e) => setTime(e.target.value)} />
              </div>
            )}
          </div>
          {type === "weekly" && (
            <div className="flex flex-wrap gap-1.5">
              {DAYS.map((d, i) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDays(days.includes(i) ? days.filter((x) => x !== i) : [...days, i].sort())}
                  className={cn(
                    "rounded-full border px-3 py-1 text-sm",
                    days.includes(i) ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
                  )}
                >
                  {d}
                </button>
              ))}
            </div>
          )}
          <div className="bg-muted/50 text-muted-foreground rounded-xl p-3 text-xs">
            <p className="text-foreground font-medium">
              {preview.data?.description ?? "…"} <span className="text-muted-foreground font-normal">({timezone})</span>
            </p>
            {preview.error ? (
              <p className="text-destructive mt-1">{preview.error.message}</p>
            ) : (
              <p className="mt-1">
                Next:{" "}
                {preview.data?.next_runs
                  .slice(0, 3)
                  .map((r) => formatDateTime(r))
                  .join(" · ") || "-"}
              </p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={save}
            disabled={
              create.isPending ||
              !schedule ||
              Boolean(preview.error) ||
              (kind === "reminder" && !message.trim()) ||
              (kind === "assistant_prompt" && !prompt.trim())
            }
          >
            {create.isPending && <Loader2 className="animate-spin" />} Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RunHistory({ id }: { id: string }) {
  const runs = useAutomationRuns(id);
  if (runs.isPending) return <Skeleton className="h-16" />;
  if (!runs.data?.items.length) return <p className="text-muted-foreground text-sm">No runs yet.</p>;
  return (
    <ul className="divide-y text-sm">
      {runs.data.items.map((r) => (
        <li key={r.id} className="flex flex-wrap items-center gap-2 py-2">
          <StatusBadge status={r.status} />
          <span className="text-muted-foreground">{formatDateTime(r.scheduled_for ?? r.created_at)}</span>
          {r.attempt > 1 && <span className="text-muted-foreground text-xs">attempt {r.attempt}</span>}
          {r.error && <span className="text-destructive w-full text-xs">{r.error}</span>}
          {typeof r.result?.text === "string" && (
            <span className="text-muted-foreground line-clamp-2 w-full text-xs">{r.result.text}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function AutomationRow({ rule }: { rule: Automation }) {
  const { update, runNow, remove } = useAutomationMutations();
  const [expanded, setExpanded] = useState(false);
  const meta = KINDS[rule.kind];
  return (
    <li className="glass hover:border-brand/40 rounded-2xl transition-colors">
      <div className="flex items-center gap-3 p-4">
        <IconTile icon={meta.icon} tone={KIND_TONES[rule.kind]} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{rule.name}</p>
          <p className="text-muted-foreground truncate text-xs">
            {rule.schedule_description} · {rule.next_run_at ? `next ${formatDateTime(rule.next_run_at)}` : "completed"}
            {rule.last_run_at && ` · last ran ${timeAgo(rule.last_run_at)}`}
          </p>
        </div>
        {rule.last_status && <StatusBadge status={rule.last_status} className="hidden sm:inline-flex" />}
        <Switch
          checked={rule.enabled}
          onCheckedChange={(v) => update.mutate({ id: rule.id, enabled: v })}
          aria-label="Enabled"
        />
        <Button size="icon-sm" variant="ghost" onClick={() => setExpanded(!expanded)} aria-label="Details">
          <ChevronDown className={cn("transition-transform", expanded && "rotate-180")} />
        </Button>
      </div>
      {expanded && (
        <div className="space-y-3 border-t p-4">
          {rule.consecutive_failures > 0 && (
            <p className="text-destructive text-sm">
              {rule.consecutive_failures} consecutive failure(s). Check the run history below.
            </p>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                runNow.mutate(rule.id, { onSuccess: () => toast.success("Queued. It runs within a few seconds.") })
              }
            >
              <Play /> Run now
            </Button>
            <Button size="sm" variant="ghost" onClick={() => remove.mutate(rule.id)}>
              <Trash2 /> Delete
            </Button>
          </div>
          <RunHistory id={rule.id} />
        </div>
      )}
    </li>
  );
}

function AutomationsInner() {
  const params = useSearchParams();
  const automations = useAutomations();
  const initialKind = (params.get("new") as AutomationKind | null) ?? undefined;
  const [open, setOpen] = useState(Boolean(initialKind));

  return (
    <div>
      <PageHeader
        tone="amber"
        title="Automations"
        icon={Workflow}
        description="Scheduled briefings, summaries, reminders and assistant tasks. Times use your timezone."
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus /> New automation
          </Button>
        }
      />
      {automations.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : automations.error ? (
        <ErrorState error={automations.error} onRetry={() => automations.refetch()} />
      ) : automations.data?.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          tone="amber"
          title="No automations yet"
          description="Try a daily morning briefing at 7:30, or say “remind me to call my client tomorrow” in chat."
          action={
            <Button onClick={() => setOpen(true)}>
              <Plus /> Create one
            </Button>
          }
        />
      ) : (
        <ul className="space-y-2">
          {automations.data?.map((r) => (
            <AutomationRow key={r.id} rule={r} />
          ))}
        </ul>
      )}
      {open && <CreateDialog open={open} onOpenChange={setOpen} initialKind={initialKind} />}
    </div>
  );
}

export default function AutomationsPage() {
  return (
    <Suspense>
      <AutomationsInner />
    </Suspense>
  );
}
