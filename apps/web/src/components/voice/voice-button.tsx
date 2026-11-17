"use client";

import { useCallback } from "react";

import { VoiceOrb, type OrbState } from "@/components/voice/voice-orb";
import { useMe } from "@/lib/api/hooks";
import { useVoice } from "@/lib/voice/voice-provider";
import { useVoiceStore } from "@/lib/voice/voice-store";
import { cn } from "@/lib/utils";

/** Starts a push-to-talk session honouring the user's hold-to-talk preference. */
export function useStartVoice() {
  const voice = useVoice();
  const me = useMe();
  const holdToTalk = Boolean(me.data?.preferences.push_to_talk_enabled);
  return useCallback(
    (conversationId?: string | null) => voice.start("push_to_talk", { conversationId, holdToTalk }),
    [voice, holdToTalk],
  );
}

export function VoiceButton({
  conversationId,
  size = "md",
  className,
  label = true,
}: {
  conversationId?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: boolean;
}) {
  const start = useStartVoice();
  const status = useVoiceStore((s) => s.status);
  const set = useVoiceStore((s) => s.set);
  const busy = status !== "idle" && status !== "error";
  const orb: OrbState = status === "requesting" || status === "connecting" ? "connecting" : busy ? "listening" : "idle";

  return (
    <button
      type="button"
      onClick={() => (busy ? set({ panelOpen: true }) : void start(conversationId))}
      className={cn(
        "group focus-visible:ring-ring/40 flex flex-col items-center gap-3 rounded-full outline-none focus-visible:ring-4",
        className,
      )}
      aria-label={busy ? "Open voice session" : "Talk to Nexora"}
    >
      <VoiceOrb state={orb} size={size} className="transition-transform group-hover:scale-105 group-active:scale-95" />
      {label && (
        <span className="text-muted-foreground group-hover:text-foreground text-sm font-medium">
          {busy ? "Voice session active" : "Tap to talk"}
        </span>
      )}
    </button>
  );
}
