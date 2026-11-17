"use client";

import {
  Bell,
  Command as CommandIcon,
  Compass,
  Cpu,
  Ear,
  EarOff,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  Mic,
  Monitor,
  Moon,
  Search,
  Settings,
  Sun,
  WifiOff,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Suspense, useEffect, useState, type ReactNode } from "react";

import { CommandPalette } from "@/components/app-shell/command-palette";
import { GROUP_LABELS, NAV } from "@/components/app-shell/nav";
import { Logo, Spinner, TONES } from "@/components/common";
import { AuroraBackground } from "@/components/fx/aurora-background";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { VoiceButton } from "@/components/voice/voice-button";
import { useMe, useSystemStatus, useUnreadCount } from "@/lib/api/hooks";
import { useMounted } from "@/hooks/use-mounted";
import { useAuth } from "@/lib/auth/auth-provider";
import { VoiceProvider } from "@/lib/voice/voice-provider";
import { useVoiceStore } from "@/lib/voice/voice-store";
import { cn } from "@/lib/utils";

// Voice UI depends on browser-only APIs (WebRTC, microphone, LiveKit hooks), so it is never prerendered.
const VoicePanel = dynamic(() => import("@/components/voice/voice-panel").then((m) => m.VoicePanel), { ssr: false });
const WakeWordListener = dynamic(
  () => import("@/components/voice/wake-word-listener").then((m) => m.WakeWordListener),
  { ssr: false },
);

function NavSkeleton() {
  return (
    <div className="space-y-2 px-1" aria-hidden>
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className="bg-muted/60 h-9 animate-pulse rounded-xl" />
      ))}
    </div>
  );
}

function NavLinks({ onNavigate, layoutId = "nav-pill" }: { onNavigate?: () => void; layoutId?: string }) {
  const pathname = usePathname();
  const unread = useUnreadCount().data?.count ?? 0;
  const groups = ["main", "personal", "activity", "system"] as const;
  return (
    <nav className="space-y-5">
      {groups.map((group) => (
        <div key={group}>
          {GROUP_LABELS[group] && (
            <p className="text-muted-foreground/80 mb-1.5 px-3 text-[0.68rem] font-semibold tracking-[0.16em] uppercase">
              {GROUP_LABELS[group]}
            </p>
          )}
          <ul className="space-y-0.5">
            {NAV.filter((n) => n.group === group).map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              const t = TONES[item.tone];
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "group relative flex items-center gap-3 rounded-xl px-2.5 py-2 text-sm transition-colors",
                      active ? "text-foreground font-medium" : "text-sidebar-foreground/75 hover:text-foreground",
                    )}
                  >
                    {active && (
                      <motion.span
                        layoutId={layoutId}
                        className="bg-sidebar-accent absolute inset-0 rounded-xl border border-white/10 shadow-sm"
                        transition={{ type: "spring", stiffness: 380, damping: 32 }}
                      />
                    )}
                    <span
                      className="relative grid size-7 shrink-0 place-items-center rounded-lg transition-transform group-hover:scale-110"
                      style={
                        active
                          ? {
                              background: `linear-gradient(140deg, ${t.from}, ${t.to})`,
                              boxShadow: `0 6px 16px -6px ${t.glow}`,
                              color: "white",
                            }
                          : { background: `${t.from}1f`, color: t.from }
                      }
                    >
                      <Icon className="size-4" />
                    </span>
                    <span className="relative flex-1">{item.label}</span>
                    {item.href === "/notifications" && unread > 0 && (
                      <Badge className="relative h-5 min-w-5 rounded-full bg-rose-500 px-1.5 text-[0.7rem] text-white">
                        {unread > 99 ? "99+" : unread}
                      </Badge>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

/** Live status of the assistant's engines, so the sidebar shows something useful. */
function AssistantStatusCard() {
  const status = useSystemStatus();
  const me = useMe();
  // The offline intent router is always "available", but it is not a language model.
  const llmOn = Boolean(status.data?.llm.primary_available && status.data.llm.primary !== "offline");
  const voiceOn = status.data?.voice.livekit;
  const rows = [
    {
      icon: Cpu,
      label: llmOn ? "Local AI online" : "Offline mode",
      hint: llmOn ? (status.data?.llm.model ?? "") : "Start Ollama for full AI answers",
      ok: llmOn,
    },
    {
      icon: Mic,
      label: voiceOn ? "Voice ready" : "Voice not set up",
      hint: voiceOn ? "Tap the orb to talk" : "Add LiveKit keys to enable",
      ok: voiceOn,
    },
  ];
  return (
    <div className="glass gradient-border relative overflow-hidden rounded-2xl p-3">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-10 -right-10 size-28 rounded-full opacity-60 blur-2xl"
        style={{ background: TONES.violet.glow }}
      />
      <p className="relative mb-2 text-xs font-semibold">
        Hi, {me.data?.profile.display_name ?? "there"}{" "}
        <span className="inline-block animate-[float_3s_ease-in-out_infinite]">👋</span>
      </p>
      <ul className="relative space-y-1.5">
        {rows.map((r) => (
          <li key={r.label} className="flex items-start gap-2.5">
            <span className="relative mt-1 flex size-2 shrink-0">
              {r.ok && (
                <span className="animate-pulse-ring absolute inline-flex size-full rounded-full bg-emerald-400" />
              )}
              <span
                className={cn("relative inline-flex size-2 rounded-full", r.ok ? "bg-emerald-400" : "bg-amber-400")}
              />
            </span>
            <span className="min-w-0">
              <span className="block text-xs font-medium">{r.label}</span>
              <span className="text-muted-foreground block truncate text-[0.7rem]">{r.hint}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();
  const dark = !mounted || resolvedTheme !== "light";
  return (
    <Button
      variant="ghost"
      size="icon"
      className="relative overflow-hidden rounded-full"
      onClick={() => setTheme(dark ? "light" : "dark")}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={dark ? "moon" : "sun"}
          initial={{ y: 14, rotate: -90, opacity: 0 }}
          animate={{ y: 0, rotate: 0, opacity: 1 }}
          exit={{ y: -14, rotate: 90, opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="grid place-items-center"
        >
          {dark ? <Moon className="size-4" /> : <Sun className="size-4" />}
        </motion.span>
      </AnimatePresence>
    </Button>
  );
}

function UserMenu() {
  const { user, signOut } = useAuth();
  const { setTheme } = useTheme();
  const me = useMe();
  const name = me.data?.profile.display_name || user?.email || "You";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="rounded-full" aria-label="Account menu">
          <Avatar className="ring-brand/40 size-8 ring-2">
            <AvatarFallback className="brand-gradient text-xs font-semibold text-white">
              {name.slice(0, 2).toUpperCase()}
            </AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="truncate">
          <span className="block font-medium">{name}</span>
          <span className="text-muted-foreground block truncate text-xs font-normal">{user?.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings">
            <Settings /> Settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => setTheme("light")}>
          <Sun /> Light
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>
          <Moon /> Dark
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>
          <Monitor /> System
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => void signOut()} variant="destructive">
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function WakeWordIndicator() {
  const state = useVoiceStore((s) => s.wakeWord);
  const error = useVoiceStore((s) => s.wakeWordError);
  if (state === "off") return null;
  const listening = state === "listening";
  const text =
    state === "listening"
      ? "Listening on this device for “Hey Nexora”. Audio stays on your device until it's detected."
      : state === "unconfigured"
        ? "Wake word is on, but its model isn't installed yet (see Settings)."
        : state === "paused"
          ? "Wake word paused (tab hidden or voice session active)."
          : state === "error"
            ? `Wake word error: ${error}`
            : "Starting wake word…";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs backdrop-blur",
            listening ? "border-brand/40 bg-brand-soft text-brand" : "text-muted-foreground",
          )}
        >
          {listening ? <Ear className="size-3.5" /> : <EarOff className="size-3.5" />}
          <span className="hidden sm:inline">{listening ? "Hey Nexora" : "Wake word"}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{text}</TooltipContent>
    </Tooltip>
  );
}

function OfflineBadge() {
  const status = useSystemStatus();
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  if (!online) {
    return (
      <Badge variant="outline" className="border-destructive/40 text-destructive gap-1">
        <WifiOff className="size-3" /> Offline
      </Badge>
    );
  }
  const llm = status.data?.llm;
  if (llm && (!llm.primary_available || llm.primary === "offline")) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge variant="outline" className="border-warning/40 bg-warning/10 text-warning hidden sm:inline-flex">
            Limited mode
          </Badge>
        </TooltipTrigger>
        <TooltipContent className="max-w-72">
          {llm.primary === "offline"
            ? "No language model is configured, so Nexora answers clear requests with tools and templates."
            : `The local model (${llm.model}) isn't reachable. Nexora falls back to ${llm.providers.slice(1).join(", ")}.`}{" "}
          Offline answers are templated, not AI-generated.
        </TooltipContent>
      </Tooltip>
    );
  }
  return null;
}

function PageTitle() {
  const pathname = usePathname();
  const item = NAV.find((n) => pathname === n.href || pathname.startsWith(`${n.href}/`));
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.p
        key={item?.label ?? "nexora"}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.2 }}
        className="font-heading hidden text-sm font-semibold lg:block"
      >
        {item?.label ?? "Nexora"}
      </motion.p>
    </AnimatePresence>
  );
}

function MobileTabBar() {
  const pathname = usePathname();
  const items = [
    { href: "/dashboard", icon: LayoutDashboard, label: "Home" },
    { href: "/assistant", icon: MessageSquare, label: "Chat" },
    null,
    { href: "/discover", icon: Compass, label: "Discover" },
    { href: "/notifications", icon: Bell, label: "Alerts" },
  ];
  return (
    <nav className="glass-strong fixed inset-x-3 bottom-3 z-40 rounded-3xl pb-[env(safe-area-inset-bottom)] md:hidden">
      <ul className="grid grid-cols-5 items-end">
        {items.map((item) =>
          item === null ? (
            <li key="voice" className="flex justify-center">
              <VoiceButton size="sm" label={false} className="-translate-y-4" />
            </li>
          ) : (
            <li key={item.href}>
              <Link
                href={item.href}
                className={cn(
                  "relative flex flex-col items-center gap-0.5 py-2.5 text-[0.7rem]",
                  pathname.startsWith(item.href) ? "text-brand font-medium" : "text-muted-foreground",
                )}
              >
                {pathname.startsWith(item.href) && (
                  <motion.span layoutId="tab-dot" className="bg-brand absolute top-1 size-1 rounded-full" />
                )}
                <item.icon className="size-5" />
                {item.label}
              </Link>
            </li>
          ),
        )}
      </ul>
    </nav>
  );
}

/**
 * Sends new users to onboarding. Pages render straight away with their own loading states, so every
 * route has a real prerendered shell (and Next.js can validate instant navigation into it); only a
 * profile confirmed as "not onboarded" swaps in the spinner while redirecting.
 */
function OnboardingGate({ children }: { children: ReactNode }) {
  const me = useMe();
  const router = useRouter();
  const needsOnboarding = Boolean(me.data && !me.data.profile.onboarded_at);
  useEffect(() => {
    if (needsOnboarding) router.replace("/onboarding");
  }, [needsOnboarding, router]);
  if (needsOnboarding) {
    return (
      <div className="grid min-h-[50vh] place-items-center">
        <Spinner className="size-6" />
      </div>
    );
  }
  return <>{children}</>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const auth = useAuth();
  const router = useRouter();
  const mounted = useMounted();
  const unread = useUnreadCount().data?.count ?? 0;

  useEffect(() => {
    if (auth.status === "unauthenticated") router.replace("/login");
  }, [auth.status, router]);

  return (
    <VoiceProvider>
      <AuroraBackground />
      <div className="flex min-h-dvh">
        <aside className="sticky top-0 hidden h-dvh w-[17rem] shrink-0 p-3 md:flex">
          <div className="glass flex w-full flex-col rounded-3xl px-3 py-4">
            <Link href="/dashboard" className="mb-6 px-2">
              <Logo />
            </Link>
            <div className="-mx-1 flex-1 scrollbar-thin overflow-y-auto px-1">
              <Suspense fallback={<NavSkeleton />}>
                <NavLinks />
              </Suspense>
            </div>
            <div className="pt-3">
              <AssistantStatusCard />
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 px-3 pt-3 md:pl-0">
            <div className="glass flex h-14 items-center gap-2 rounded-2xl px-3 md:px-4">
              <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
                <SheetTrigger asChild>
                  <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
                    <Menu />
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" className="glass-strong w-72 p-4">
                  <SheetHeader className="p-0 pb-4">
                    <SheetTitle>
                      <Logo />
                    </SheetTitle>
                  </SheetHeader>
                  <Suspense fallback={<NavSkeleton />}>
                    <NavLinks onNavigate={() => setMobileOpen(false)} layoutId="nav-pill-mobile" />
                  </Suspense>
                </SheetContent>
              </Sheet>
              <Link href="/dashboard" className="md:hidden">
                <Logo withText={false} />
              </Link>
              <Suspense>
                <PageTitle />
              </Suspense>
              <button
                type="button"
                onClick={() => setPaletteOpen(true)}
                className="bg-background/40 text-muted-foreground hover:border-brand/40 hover:text-foreground mx-auto flex h-9 w-full max-w-md items-center gap-2 rounded-xl border px-3 text-sm transition-colors"
              >
                <Search className="size-4" />
                <span className="truncate">Search or ask Nexora…</span>
                <kbd className="bg-muted ml-auto hidden items-center gap-0.5 rounded-md px-1.5 py-0.5 font-mono text-[0.7rem] sm:inline-flex">
                  <CommandIcon className="size-3" />K
                </kbd>
              </button>
              <OfflineBadge />
              <WakeWordIndicator />
              <ThemeToggle />
              <Button
                asChild
                variant="ghost"
                size="icon"
                className="relative hidden rounded-full md:inline-flex"
                aria-label="Notifications"
              >
                <Link href="/notifications">
                  <Bell />
                  {unread > 0 && (
                    <span className="absolute top-1.5 right-1.5 flex size-2">
                      <span className="animate-pulse-ring absolute inline-flex size-full rounded-full bg-rose-500" />
                      <span className="relative inline-flex size-2 rounded-full bg-rose-500" />
                    </span>
                  )}
                </Link>
              </Button>
              <UserMenu />
            </div>
          </header>
          <main className="mx-auto w-full max-w-7xl flex-1 px-3 pt-5 pb-28 md:pr-6 md:pb-10 md:pl-3">
            <OnboardingGate>{children}</OnboardingGate>
          </main>
        </div>
      </div>
      <Suspense>
        <MobileTabBar />
      </Suspense>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      {/* Browser-only (LiveKit, microphone, on-device wake word). Mounting them after hydration keeps
          the shared layout free of server-side "browser-only" bailouts. */}
      {mounted && (
        <>
          <VoicePanel />
          <WakeWordListener />
        </>
      )}
    </VoiceProvider>
  );
}
