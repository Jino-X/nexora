"use client";

import { Loader2, Mic } from "lucide-react";

import { cn } from "@/lib/utils";

export type OrbState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "muted" | "error";

const RING: Record<OrbState, string> = {
  idle: "opacity-0",
  connecting: "opacity-60 animate-orb-spin",
  listening: "opacity-100 animate-orb-breathe",
  thinking: "opacity-80 animate-orb-spin",
  speaking: "opacity-100 animate-orb-pulse",
  muted: "opacity-30",
  error: "opacity-0",
};

export function VoiceOrb({
  state,
  size = "md",
  className,
  level = 0,
}: {
  state: OrbState;
  size?: "sm" | "md" | "lg";
  className?: string;
  level?: number;
}) {
  const dims = size === "lg" ? "size-36" : size === "md" ? "size-20" : "size-11";
  const icon = size === "lg" ? "size-10" : size === "md" ? "size-7" : "size-5";
  return (
    <span className={cn("relative grid place-items-center", dims, className)} aria-hidden>
      <span
        className={cn(
          "absolute -inset-3 rounded-full bg-[conic-gradient(from_0deg,oklch(0.7_0.2_300),oklch(0.62_0.2_250),oklch(0.72_0.15_200),oklch(0.7_0.2_300))] blur-xl transition-opacity",
          RING[state],
        )}
      />
      <span
        className="brand-gradient absolute inset-0 rounded-full shadow-lg ring-1 ring-white/25 transition-transform duration-150"
        style={{ transform: `scale(${1 + Math.min(level, 1) * 0.12})` }}
      />
      <span className="absolute inset-[18%] rounded-full bg-white/10 backdrop-blur-sm" />
      <span className="relative text-white">
        {state === "connecting" || state === "thinking" ? (
          <Loader2 className={cn(icon, "animate-spin")} />
        ) : state === "speaking" ? (
          <span className="flex items-end gap-[3px]">
            {[0, 1, 2, 3].map((i) => (
              <span
                key={i}
                className="animate-orb-pulse w-[3px] rounded-full bg-white"
                style={{ height: size === "lg" ? 22 + (i % 2) * 10 : 10 + (i % 2) * 5, animationDelay: `${i * 120}ms` }}
              />
            ))}
          </span>
        ) : (
          <Mic className={icon} />
        )}
      </span>
    </span>
  );
}
