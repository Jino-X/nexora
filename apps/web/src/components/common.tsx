"use client";

import { AlertTriangle, Loader2, PlugZap, RefreshCw, type LucideIcon } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/** Colour families used for icon tiles, so each area of the app has its own identity. */
export const TONES = {
  violet: { from: "#8b5cf6", to: "#6366f1", glow: "rgba(139,92,246,0.45)" },
  cyan: { from: "#22d3ee", to: "#3b82f6", glow: "rgba(34,211,238,0.4)" },
  pink: { from: "#f472b6", to: "#a855f7", glow: "rgba(244,114,182,0.42)" },
  amber: { from: "#fbbf24", to: "#f97316", glow: "rgba(251,191,36,0.4)" },
  emerald: { from: "#34d399", to: "#0d9488", glow: "rgba(52,211,153,0.4)" },
  rose: { from: "#fb7185", to: "#e11d48", glow: "rgba(251,113,133,0.42)" },
  sky: { from: "#38bdf8", to: "#6366f1", glow: "rgba(56,189,248,0.4)" },
  lime: { from: "#a3e635", to: "#16a34a", glow: "rgba(163,230,53,0.38)" },
} as const;

export type Tone = keyof typeof TONES;

/** Glossy 3D-style icon tile: gradient body, inner highlight, coloured glow. */
export function IconTile({
  icon: Icon,
  tone = "violet",
  size = "md",
  className,
}: {
  icon: LucideIcon;
  tone?: Tone;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}) {
  const t = TONES[tone];
  const dims = {
    sm: "size-8 rounded-lg",
    md: "size-10 rounded-xl",
    lg: "size-12 rounded-2xl",
    xl: "size-16 rounded-3xl",
  }[size];
  const icon = { sm: "size-4", md: "size-5", lg: "size-6", xl: "size-8" }[size];
  return (
    <span
      className={cn("relative grid shrink-0 place-items-center text-white", dims, className)}
      style={{
        background: `linear-gradient(140deg, ${t.from}, ${t.to})`,
        boxShadow: `0 8px 24px -8px ${t.glow}, inset 0 1px 0 rgba(255,255,255,0.35), inset 0 -6px 12px rgba(0,0,0,0.12)`,
      }}
    >
      <span
        aria-hidden
        className="absolute inset-x-[12%] top-[6%] h-[38%] rounded-[inherit] bg-gradient-to-b from-white/35 to-transparent"
      />
      <Icon className={cn("relative drop-shadow-sm", icon)} />
    </span>
  );
}

export function Logo({ className, withText = true }: { className?: string; withText?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <span className="relative grid size-9 place-items-center">
        <span aria-hidden className="absolute inset-0 rounded-xl bg-[#7c4dff] opacity-60 blur-md" />
        <span className="brand-gradient relative grid size-9 place-items-center rounded-xl ring-1 ring-white/25">
          <span
            aria-hidden
            className="absolute inset-x-1 top-0.5 h-1/2 rounded-[10px] bg-gradient-to-b from-white/35 to-transparent"
          />
          <svg viewBox="0 0 24 24" className="relative size-[18px] text-white" fill="none" aria-hidden>
            <path
              d="M5 18V6l14 12V6"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </span>
      {withText && <span className="font-heading text-[1.15rem] font-semibold tracking-tight">Nexora</span>}
    </span>
  );
}

/** Hero-style page header: glass banner, floating icon tile, ambient glow and optional stats. */
export function PageHeader({
  title,
  description,
  icon: Icon,
  actions,
  tone = "violet",
  eyebrow,
  children,
}: {
  title: string;
  description?: ReactNode;
  icon?: LucideIcon;
  actions?: ReactNode;
  tone?: Tone;
  eyebrow?: string;
  children?: ReactNode;
}) {
  const reduce = useReducedMotion();
  const t = TONES[tone];
  return (
    <motion.header
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 220, damping: 26 }}
      className="glass gradient-border relative mb-6 overflow-hidden rounded-3xl p-5 sm:p-7"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 -right-16 size-72 rounded-full opacity-50 blur-3xl"
        style={{ background: t.glow }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-28 left-1/3 size-64 rounded-full opacity-30 blur-3xl"
        style={{ background: TONES.cyan.glow }}
      />
      <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          {Icon && <IconTile icon={Icon} tone={tone} size="xl" className="animate-float" />}
          <div>
            {eyebrow && (
              <p className="text-muted-foreground mb-1 text-xs font-medium tracking-[0.14em] uppercase">{eyebrow}</p>
            )}
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
            {description && <p className="text-muted-foreground mt-1.5 max-w-2xl text-sm">{description}</p>}
          </div>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children && <div className="relative mt-5">{children}</div>}
    </motion.header>
  );
}

/** Small stat pill for page headers. */
export function HeaderStat({ label, value, icon: Icon }: { label: string; value: ReactNode; icon?: LucideIcon }) {
  return (
    <div className="bg-background/40 flex items-center gap-2.5 rounded-2xl border px-3.5 py-2 backdrop-blur">
      {Icon && <Icon className="text-brand size-4" />}
      <span className="text-lg font-semibold tabular-nums">{value}</span>
      <span className="text-muted-foreground text-xs">{label}</span>
    </div>
  );
}

/** Animated illustration instead of a blank dashed box. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  tone = "violet",
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  tone?: Tone;
}) {
  const t = TONES[tone];
  return (
    <div
      className={cn(
        "glass relative flex flex-col items-center justify-center overflow-hidden rounded-3xl px-6 py-14 text-center",
        className,
      )}
    >
      <div
        aria-hidden
        className="bg-dots absolute inset-0 [mask-image:radial-gradient(circle,black,transparent_70%)]"
      />
      <div className="relative mb-5 grid size-28 place-items-center">
        <span
          aria-hidden
          className="absolute inset-0 rounded-full opacity-60 blur-2xl"
          style={{ background: t.glow }}
        />
        <span aria-hidden className="border-border absolute inset-1 rounded-full border border-dashed" />
        <span aria-hidden className="animate-spin-slow absolute inset-1 rounded-full">
          <span
            className="absolute -top-1 left-1/2 size-2.5 -translate-x-1/2 rounded-full"
            style={{ background: t.from, boxShadow: `0 0 12px ${t.glow}` }}
          />
          <span
            className="absolute bottom-3 -left-0.5 size-1.5 rounded-full"
            style={{ background: t.to, boxShadow: `0 0 10px ${t.glow}` }}
          />
        </span>
        <IconTile icon={Icon} tone={tone} size="lg" className="animate-float" />
      </div>
      <p className="relative text-base font-semibold">{title}</p>
      {description && <p className="text-muted-foreground relative mt-1.5 max-w-sm text-sm">{description}</p>}
      {action && <div className="relative mt-5">{action}</div>}
    </div>
  );
}

/** Honest error display: distinguishes "not configured" (503) from failures. */
export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const api = error instanceof ApiError ? error : null;
  if (api?.isNotConfigured) {
    return (
      <div className={cn("glass flex items-start gap-3 rounded-2xl p-4", className)}>
        <IconTile icon={PlugZap} tone="amber" size="sm" />
        <div className="text-sm">
          <p className="font-medium">Not configured</p>
          <p className="text-muted-foreground mt-0.5">{api.message}</p>
          <Link href="/integrations" className="text-brand mt-2 inline-block underline-offset-2 hover:underline">
            See integrations
          </Link>
        </div>
      </div>
    );
  }
  return (
    <div
      className={cn(
        "border-destructive/30 bg-destructive/10 flex items-start gap-3 rounded-2xl border p-4 backdrop-blur",
        className,
      )}
    >
      <AlertTriangle className="text-destructive mt-0.5 size-5 shrink-0" />
      <div className="flex-1 text-sm">
        <p className="font-medium">Something went wrong</p>
        <p className="text-muted-foreground mt-0.5">{error instanceof Error ? error.message : "Unknown error"}</p>
      </div>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          <RefreshCw /> Retry
        </Button>
      )}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("text-muted-foreground size-4 animate-spin", className)} />;
}

const STATUS_STYLES: Record<string, string> = {
  connected: "bg-success/15 text-success border-success/30",
  ready: "bg-success/15 text-success border-success/30",
  succeeded: "bg-success/15 text-success border-success/30",
  executed: "bg-success/15 text-success border-success/30",
  active: "bg-success/15 text-success border-success/30",
  pending: "bg-warning/15 text-warning border-warning/30",
  running: "bg-brand-soft text-brand border-brand/30",
  retrying: "bg-warning/15 text-warning border-warning/30",
  queued: "bg-muted text-muted-foreground",
  failed: "bg-destructive/10 text-destructive border-destructive/30",
  error: "bg-destructive/10 text-destructive border-destructive/30",
  rejected: "bg-muted text-muted-foreground",
  expired: "bg-muted text-muted-foreground",
  disconnected: "bg-muted text-muted-foreground",
  not_configured: "bg-muted text-muted-foreground",
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const live = ["connected", "ready", "active", "running"].includes(status);
  return (
    <Badge variant="outline" className={cn("gap-1.5 capitalize", STATUS_STYLES[status] ?? "", className)}>
      {live && (
        <span className="relative flex size-1.5">
          <span className="animate-pulse-ring absolute inline-flex size-full rounded-full bg-current" />
          <span className="relative inline-flex size-1.5 rounded-full bg-current" />
        </span>
      )}
      {status.replace(/_/g, " ")}
    </Badge>
  );
}
