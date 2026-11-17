"use client";

import {
  ArrowRight,
  ArrowUp,
  Bell,
  Brain,
  CalendarClock,
  CloudSun,
  Compass,
  Fuel,
  Hotel,
  ListChecks,
  Mail,
  MessageSquare,
  MonitorPlay,
  Music,
  Newspaper,
  Plug,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

import { ApprovalCard } from "@/components/assistant/approval-card";
import { WeatherCard } from "@/components/assistant/result-cards";
import { EmptyState, ErrorState, IconTile, StatusBadge, type Tone } from "@/components/common";
import { AnimatedNumber, Reveal, Stagger, StaggerItem } from "@/components/fx/motion";
import { Orb3D } from "@/components/fx/orb-3d";
import { TiltCard } from "@/components/fx/tilt-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useStartVoice } from "@/components/voice/voice-button";
import { useDashboard, useIntegrations, useMe, useWeather } from "@/lib/api/hooks";
import { useToday } from "@/hooks/use-today";
import { formatDateTime, timeAgo } from "@/lib/format";
import { useVoiceStore } from "@/lib/voice/voice-store";
import { cn } from "@/lib/utils";

const QUICK_ACTIONS: { label: string; icon: typeof CloudSun; prompt: string; tone: Tone }[] = [
  { label: "Weather", icon: CloudSun, prompt: "What's the weather today?", tone: "amber" },
  { label: "AI news", icon: Newspaper, prompt: "Give me today's important AI news", tone: "sky" },
  { label: "Petrol pump", icon: Fuel, prompt: "Find a petrol pump near me", tone: "rose" },
  { label: "Hotels", icon: Hotel, prompt: "Find hotels near this location", tone: "pink" },
  { label: "Unread email", icon: Mail, prompt: "Summarize my unread emails", tone: "violet" },
  { label: "YouTube", icon: MonitorPlay, prompt: "Search YouTube for React tutorials", tone: "rose" },
  { label: "Music", icon: Music, prompt: "Play some relaxing music", tone: "emerald" },
  { label: "Briefing", icon: Sparkles, prompt: "Give me my daily briefing", tone: "cyan" },
];

const SUGGESTIONS = ["Remind me to call my client tomorrow at 10am", "What did I tell you about my project?"];

function Panel({
  title,
  icon,
  tone = "violet",
  action,
  children,
  className,
}: {
  title: string;
  icon: typeof Bell;
  tone?: Tone;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("glass relative flex flex-col overflow-hidden rounded-3xl p-5", className)}>
      <header className="mb-4 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2.5 text-sm font-semibold">
          <IconTile icon={icon} tone={tone} size="sm" />
          {title}
        </h2>
        {action}
      </header>
      <div className="flex-1">{children}</div>
    </section>
  );
}

function StatCard({
  label,
  value,
  icon,
  tone,
  href,
  hint,
}: {
  label: string;
  value: number;
  icon: typeof Bell;
  tone: Tone;
  href: string;
  hint: string;
}) {
  return (
    <Link href={href} className="block">
      <TiltCard className="glass h-full rounded-3xl p-4">
        <div className="flex items-start justify-between">
          <IconTile icon={icon} tone={tone} />
          <ArrowRight className="text-muted-foreground size-4 opacity-0 transition-opacity group-hover/tilt:opacity-100" />
        </div>
        <p className="mt-4 text-3xl font-semibold tracking-tight tabular-nums">
          <AnimatedNumber value={value} />
        </p>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-muted-foreground text-xs">{hint}</p>
      </TiltCard>
    </Link>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const me = useMe();
  const dash = useDashboard();
  const prefs = me.data?.preferences;
  const hasHome = prefs?.home_latitude != null;
  const weather = useWeather(null, null, hasHome);
  const integrations = useIntegrations();
  const startVoice = useStartVoice();
  const voiceStatus = useVoiceStore((s) => s.status);
  const setVoice = useVoiceStore((s) => s.set);
  const [prompt, setPrompt] = useState("");
  const name = me.data?.profile.display_name;
  const today = useToday();
  const d = dash.data;
  const busy = voiceStatus !== "idle" && voiceStatus !== "error";

  function ask(text: string) {
    router.push(`/assistant?prompt=${encodeURIComponent(text)}`);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (prompt.trim()) ask(prompt.trim());
  }

  return (
    <div className="space-y-5">
      {/* Hero */}
      <Reveal>
        <section className="glass gradient-border relative overflow-hidden rounded-[2rem] p-6 sm:p-10">
          <div aria-hidden className="pointer-events-none absolute inset-0">
            <div className="absolute -top-32 -left-24 size-96 rounded-full bg-violet-500/25 blur-3xl" />
            <div className="absolute -right-10 -bottom-40 size-[28rem] rounded-full bg-cyan-400/20 blur-3xl" />
            <div className="bg-dots absolute inset-0 [mask-image:linear-gradient(to_right,transparent,black_40%,black_70%,transparent)]" />
          </div>
          <div className="relative grid items-center gap-8 lg:grid-cols-[1.25fr_1fr]">
            <div>
              <p className="bg-background/40 text-muted-foreground inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs backdrop-blur">
                <span className="relative flex size-2">
                  <span className="animate-pulse-ring absolute inline-flex size-full rounded-full bg-emerald-400" />
                  <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
                </span>
                {today?.date ?? "Today"}
              </p>
              <h1 className="mt-4 text-4xl leading-[1.05] font-semibold tracking-tight sm:text-5xl lg:text-6xl">
                {today?.greeting ?? "Hello"},
                <br />
                <span className="text-shimmer">{name ?? "friend"}</span>
              </h1>
              <p className="text-muted-foreground mt-3 max-w-md text-base">
                Ask me anything by text or voice, or just say{" "}
                <span className="text-foreground font-medium">“Hey Nexora”</span>.
              </p>
              <form
                onSubmit={onSubmit}
                className="bg-background/50 focus-within:border-brand/50 focus-within:ring-brand/15 mt-6 flex max-w-xl items-center gap-2 rounded-2xl border p-2 pl-4 shadow-lg backdrop-blur-xl transition focus-within:ring-4"
              >
                <Sparkles className="text-brand size-5 shrink-0" />
                <input
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Find hotels near me, summarize my email…"
                  className="placeholder:text-muted-foreground min-w-0 flex-1 bg-transparent py-1.5 text-[0.95rem] outline-none"
                  aria-label="Ask Nexora"
                />
                <Button
                  type="submit"
                  size="icon-lg"
                  className="brand-gradient rounded-xl text-white"
                  disabled={!prompt.trim()}
                  aria-label="Ask"
                >
                  <ArrowUp />
                </Button>
              </form>
              <div className="mt-3 flex flex-wrap gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => ask(s)}
                    className="bg-background/40 text-muted-foreground hover:border-brand/40 hover:text-foreground rounded-full border px-3 py-1 text-xs backdrop-blur transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
            <button
              type="button"
              onClick={() => (busy ? setVoice({ panelOpen: true }) : void startVoice())}
              className="group relative mx-auto flex w-full max-w-[15rem] flex-col items-center outline-none sm:max-w-[22rem]"
              aria-label={busy ? "Open voice session" : "Talk to Nexora"}
            >
              <Orb3D
                mood={
                  voiceStatus === "requesting" || voiceStatus === "connecting"
                    ? "connecting"
                    : busy
                      ? "listening"
                      : "idle"
                }
                className="w-full transition-transform duration-500 group-hover:scale-[1.03]"
              />
              <span className="glass -mt-4 inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium shadow-lg">
                <span className="relative flex size-2">
                  <span className="animate-pulse-ring absolute inline-flex size-full rounded-full bg-violet-400" />
                  <span className="relative inline-flex size-2 rounded-full bg-violet-400" />
                </span>
                {busy ? "Voice session active" : "Tap the orb to talk"}
              </span>
            </button>
          </div>
        </section>
      </Reveal>

      {dash.error && <ErrorState error={dash.error} onRetry={() => dash.refetch()} />}

      {/* Stats */}
      <Stagger className="grid grid-cols-2 gap-3 lg:grid-cols-4" delay={0.1}>
        <StaggerItem>
          <StatCard
            label="Memories"
            value={d?.memory_count ?? 0}
            icon={Brain}
            tone="rose"
            href="/memory"
            hint="Things I remember for you"
          />
        </StaggerItem>
        <StaggerItem>
          <StatCard
            label="Automations"
            value={d?.upcoming_automations.length ?? 0}
            icon={Workflow}
            tone="amber"
            href="/automations"
            hint="Scheduled and active"
          />
        </StaggerItem>
        <StaggerItem>
          <StatCard
            label="Need approval"
            value={d?.pending_approval_count ?? 0}
            icon={ShieldCheck}
            tone="sky"
            href="/tasks"
            hint="Waiting for your OK"
          />
        </StaggerItem>
        <StaggerItem>
          <StatCard
            label="Unread alerts"
            value={d?.unread_notification_count ?? 0}
            icon={Bell}
            tone="pink"
            href="/notifications"
            hint="Reminders and updates"
          />
        </StaggerItem>
      </Stagger>

      {/* Quick actions */}
      <section aria-label="Quick actions">
        <h2 className="text-muted-foreground mb-3 px-1 text-xs font-semibold tracking-[0.16em] uppercase">
          Quick actions
        </h2>
        <Stagger className="grid grid-cols-4 gap-2.5 sm:grid-cols-8" delay={0.2}>
          {QUICK_ACTIONS.map((a) => (
            <StaggerItem key={a.label}>
              <TiltCard
                as="button"
                onClick={() => ask(a.prompt)}
                max={12}
                className="glass flex w-full flex-col items-center gap-2.5 rounded-2xl px-2 py-4 text-xs font-medium"
              >
                <IconTile icon={a.icon} tone={a.tone} size="lg" />
                {a.label}
              </TiltCard>
            </StaggerItem>
          ))}
        </Stagger>
      </section>

      {/* Bento */}
      <div className="grid gap-4 lg:grid-cols-12">
        <Panel
          title="Today's briefing"
          icon={Sparkles}
          tone="violet"
          className="gradient-border lg:col-span-7"
          action={
            <Button size="sm" variant="ghost" onClick={() => ask("Give me my daily briefing")}>
              Generate now <ArrowRight />
            </Button>
          }
        >
          {dash.isPending ? (
            <Skeleton className="h-32 rounded-2xl" />
          ) : d?.latest_briefing ? (
            <div>
              <p className="text-[1.02rem] leading-relaxed">{d.latest_briefing.text}</p>
              <p className="text-muted-foreground mt-3 text-xs">Generated {timeAgo(d.latest_briefing.generated_at)}</p>
            </div>
          ) : (
            <div className="relative flex h-full flex-col justify-between gap-5 sm:flex-row sm:items-center">
              <div>
                <p className="text-lg font-semibold">Start every morning in one glance</p>
                <p className="text-muted-foreground mt-1 max-w-sm text-sm">
                  Weather, headlines you care about, unread email and today&apos;s reminders, ready when you wake up.
                </p>
                <Button asChild className="brand-gradient mt-4 text-white">
                  <Link href="/automations?new=morning_briefing">
                    <CalendarClock /> Set up morning briefing
                  </Link>
                </Button>
              </div>
              <div className="relative hidden size-32 shrink-0 sm:block" aria-hidden>
                <div className="absolute inset-0 rounded-full bg-gradient-to-br from-amber-300/40 to-pink-400/30 blur-2xl" />
                <IconTile icon={CloudSun} tone="amber" size="xl" className="animate-float absolute top-2 left-2" />
                <IconTile
                  icon={Newspaper}
                  tone="sky"
                  size="lg"
                  className="absolute right-0 bottom-6 animate-[float_7s_ease-in-out_infinite]"
                />
                <IconTile
                  icon={Mail}
                  tone="violet"
                  size="md"
                  className="absolute bottom-0 left-8 animate-[float_5s_ease-in-out_infinite]"
                />
              </div>
            </div>
          )}
        </Panel>

        <Panel
          title="Weather"
          icon={CloudSun}
          tone="amber"
          className="lg:col-span-5"
          action={
            <Link href="/discover/weather" className="text-brand text-xs font-medium">
              Forecast
            </Link>
          }
        >
          {!hasHome ? (
            <EmptyState
              icon={CloudSun}
              tone="amber"
              title="Set a home location"
              description="Used for weather and your briefing."
              className="py-8"
              action={
                <Button asChild size="sm" variant="outline">
                  <Link href="/settings?tab=profile">Open settings</Link>
                </Button>
              }
            />
          ) : weather.isPending ? (
            <Skeleton className="h-44 rounded-2xl" />
          ) : weather.error ? (
            <ErrorState error={weather.error} />
          ) : weather.data ? (
            <WeatherCard
              report={{ ...weather.data, location_label: prefs?.home_label ?? weather.data.location_label }}
              compact
            />
          ) : null}
        </Panel>

        <Panel
          title="Waiting for you"
          icon={ListChecks}
          tone="sky"
          className="lg:col-span-4"
          action={
            <Link href="/tasks" className="text-brand text-xs font-medium">
              All tasks
            </Link>
          }
        >
          {d?.pending_approvals.length ? (
            <div className="space-y-2">
              {d.pending_approvals.map((a) => (
                <ApprovalCard
                  key={a.id}
                  approvalId={a.id}
                  tool={a.tool_name}
                  summary={a.summary}
                  initialStatus={a.status}
                />
              ))}
            </div>
          ) : (
            <div className="bg-success/10 text-success flex items-center gap-2 rounded-2xl px-3 py-2.5 text-sm">
              <ShieldCheck className="size-4" /> Nothing needs your approval
            </div>
          )}
          {d?.recent_tasks.length ? (
            <ul className="mt-4 space-y-2.5 text-sm">
              {d.recent_tasks.slice(0, 4).map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-2">
                  <span className="truncate">{t.title || t.kind}</span>
                  <StatusBadge status={t.status} />
                </li>
              ))}
            </ul>
          ) : null}
        </Panel>

        <Panel
          title="Coming up"
          icon={Bell}
          tone="pink"
          className="lg:col-span-4"
          action={
            <Link href="/notifications" className="text-brand text-xs font-medium">
              Alerts
            </Link>
          }
        >
          {d?.upcoming_automations.length ? (
            <ol className="relative space-y-4 border-l border-dashed pl-4">
              {d.upcoming_automations.map((a) => (
                <li key={a.id} className="relative">
                  <span className="absolute top-1.5 -left-[1.3rem] size-2.5 rounded-full bg-pink-400 shadow-[0_0_10px] shadow-pink-400/60" />
                  <p className="text-sm font-medium">{a.name}</p>
                  <p className="text-muted-foreground text-xs">
                    {formatDateTime(a.next_run_at)} · {a.schedule}
                  </p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-muted-foreground text-sm">No upcoming automations.</p>
          )}
          {d?.unread_notifications.length ? (
            <ul className="mt-4 space-y-3 border-t pt-3 text-sm">
              {d.unread_notifications.slice(0, 3).map((n) => (
                <li key={n.id}>
                  <p className="font-medium">{n.title}</p>
                  <p className="text-muted-foreground line-clamp-1 text-xs">{n.body}</p>
                </li>
              ))}
            </ul>
          ) : null}
        </Panel>

        <Panel
          title="Recent conversations"
          icon={MessageSquare}
          tone="violet"
          className="lg:col-span-4"
          action={
            <Link href="/history" className="text-brand text-xs font-medium">
              History
            </Link>
          }
        >
          {d?.recent_conversations.length ? (
            <ul className="-mx-2 space-y-1 text-sm">
              {d.recent_conversations.map((c) => (
                <li key={c.id}>
                  <Link
                    href={`/assistant/${c.id}`}
                    className="hover:bg-accent group flex items-center gap-3 rounded-xl px-2 py-2 transition-colors"
                  >
                    <span className="bg-brand-soft text-brand grid size-8 shrink-0 place-items-center rounded-lg">
                      <MessageSquare className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{c.title}</span>
                      <span className="text-muted-foreground text-xs">{timeAgo(c.last_message_at)}</span>
                    </span>
                    <ArrowRight className="text-muted-foreground size-4 opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-sm">Start your first conversation above.</p>
          )}
        </Panel>

        <Panel
          title="Connected services"
          icon={Plug}
          tone="lime"
          className="lg:col-span-12"
          action={
            <Link href="/integrations" className="text-brand text-xs font-medium">
              Manage
            </Link>
          }
        >
          <div className="flex flex-wrap gap-2">
            {integrations.data?.map((i) => (
              <Link
                key={i.provider}
                href={`/integrations${["gmail", "whatsapp", "youtube", "music"].includes(i.provider) ? `/${i.provider}` : ""}`}
                className="bg-background/40 hover:border-brand/40 inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm backdrop-blur transition-colors"
              >
                {i.name}
                <StatusBadge status={i.status} />
              </Link>
            ))}
            <Link
              href="/discover"
              className="bg-background/40 hover:border-brand/40 inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm backdrop-blur"
            >
              <Compass className="size-3.5 text-cyan-400" /> Discover nearby
            </Link>
          </div>
        </Panel>
      </div>
    </div>
  );
}
