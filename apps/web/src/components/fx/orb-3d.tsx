"use client";

import { useReducedMotion } from "motion/react";
import dynamic from "next/dynamic";
import { useTheme } from "next-themes";

import type { OrbMood } from "@/components/fx/orb-scene";
import { useMounted } from "@/hooks/use-mounted";
import { VoiceOrb, type OrbState } from "@/components/voice/voice-orb";
import { cn } from "@/lib/utils";

const OrbScene = dynamic(() => import("@/components/fx/orb-scene"), {
  ssr: false,
  // Show the CSS orb while the 3D engine downloads, so the hero is never empty.
  loading: () => (
    <div className="grid size-full place-items-center">
      <VoiceOrb state="idle" size="lg" />
    </div>
  ),
});

const PALETTES: Record<"dark" | "light", Record<OrbMood, [string, string, string]>> = {
  dark: {
    idle: ["#6d3df5", "#22d3ee", "#f472b6"],
    connecting: ["#5b5bf0", "#38bdf8", "#a78bfa"],
    listening: ["#7c3aed", "#2dd4bf", "#38bdf8"],
    thinking: ["#9333ea", "#f472b6", "#60a5fa"],
    speaking: ["#6d28d9", "#22d3ee", "#e879f9"],
    muted: ["#3f3f6e", "#64748b", "#6366f1"],
  },
  light: {
    idle: ["#7c4dff", "#38bdf8", "#f472b6"],
    connecting: ["#6366f1", "#38bdf8", "#a78bfa"],
    listening: ["#7c3aed", "#14b8a6", "#38bdf8"],
    thinking: ["#9333ea", "#ec4899", "#3b82f6"],
    speaking: ["#7c3aed", "#06b6d4", "#d946ef"],
    muted: ["#6b7280", "#94a3b8", "#818cf8"],
  },
};

function toCss(mood: OrbMood): OrbState {
  if (mood === "connecting") return "connecting";
  return mood;
}

/**
 * Living 3D voice orb (WebGL). Falls back to the CSS orb when WebGL is unavailable or the user
 * prefers reduced motion. `level` (0..1) drives the surface while Nexora is speaking.
 */
export function Orb3D({
  mood = "idle",
  level = 0,
  className,
  halo = true,
}: {
  mood?: OrbMood;
  level?: number;
  className?: string;
  halo?: boolean;
}) {
  const reduce = useReducedMotion();
  const { resolvedTheme } = useTheme();
  const mounted = useMounted();
  const palette = PALETTES[mounted && resolvedTheme === "light" ? "light" : "dark"][mood];
  const fallback = <VoiceOrb state={toCss(mood)} size="lg" className="mx-auto" />;

  return (
    <div className={cn("relative aspect-square", className)}>
      {halo && (
        <div
          aria-hidden
          className="absolute inset-[8%] rounded-full opacity-70 blur-3xl transition-colors duration-700"
          style={{ background: `radial-gradient(circle, ${palette[0]}aa, ${palette[1]}55 45%, transparent 70%)` }}
        />
      )}
      <div className="absolute inset-0">
        {reduce ? (
          <div className="grid size-full place-items-center">{fallback}</div>
        ) : (
          <OrbScene mood={mood} level={level} colors={palette} fallback={fallback} />
        )}
      </div>
    </div>
  );
}
