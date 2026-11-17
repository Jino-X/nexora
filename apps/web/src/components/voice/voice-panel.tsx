"use client";

import {
  RoomAudioRenderer,
  StartAudio,
  useLocalParticipant,
  useTextStream,
  useTrackVolume,
  useTranscriptions,
  useVoiceAssistant,
} from "@livekit/components-react";
import { VOICE_PROTOCOL, type ResultCard } from "@nexora/shared-types";
import { Hand, Mic, MicOff, PhoneOff, ShieldCheck, Square, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef } from "react";

import { ApprovalCard } from "@/components/assistant/approval-card";
import { ToolChips, type ToolProgress } from "@/components/assistant/message-bubble";
import { ResultCardView } from "@/components/assistant/result-cards";
import { useStartVoice } from "@/components/voice/voice-button";
import { Orb3D } from "@/components/fx/orb-3d";
import type { OrbMood } from "@/components/fx/orb-scene";
import { VoiceOrb, type OrbState } from "@/components/voice/voice-orb";
import { Button } from "@/components/ui/button";
import { useVoice } from "@/lib/voice/voice-provider";
import { useVoiceStore } from "@/lib/voice/voice-store";
import { cn } from "@/lib/utils";

const STATE_LABEL: Record<string, string> = {
  disconnected: "Disconnected",
  connecting: "Connecting…",
  "pre-connect-buffering": "Connecting…",
  initializing: "Getting ready…",
  idle: "Ready",
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Speaking",
  failed: "Agent unavailable",
};

function useOrbState(): { orb: OrbState; label: string } {
  const status = useVoiceStore((s) => s.status);
  const muted = useVoiceStore((s) => s.micMuted);
  const { state } = useVoiceAssistant();
  if (status === "requesting" || status === "connecting" || status === "reconnecting") {
    return { orb: "connecting", label: status === "reconnecting" ? "Reconnecting…" : "Connecting…" };
  }
  if (status === "error") return { orb: "error", label: "Voice unavailable" };
  if (state === "speaking") return { orb: "speaking", label: STATE_LABEL.speaking };
  if (state === "thinking") return { orb: "thinking", label: STATE_LABEL.thinking };
  if (muted) return { orb: "muted", label: "Microphone off" };
  if (state === "listening" || state === "idle") return { orb: "listening", label: STATE_LABEL.listening };
  return { orb: "connecting", label: STATE_LABEL[state] ?? "Waiting for Nexora…" };
}

function Transcript() {
  const transcriptions = useTranscriptions();
  const { localParticipant } = useLocalParticipant();
  const bottom = useRef<HTMLDivElement>(null);
  const items = useMemo(() => transcriptions.slice(-30), [transcriptions]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items]);

  if (items.length === 0) {
    return (
      <p className="text-muted-foreground py-6 text-center text-sm">
        Try “What&apos;s the weather today?” or “இன்றைய செய்திகள் என்ன?”
      </p>
    );
  }
  return (
    <div className="max-h-64 scrollbar-thin space-y-2 overflow-y-auto pr-1">
      {items.map((t) => {
        const mine = t.participantInfo.identity === localParticipant.identity;
        return (
          <div key={t.streamInfo.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
            <p
              className={cn(
                "max-w-[85%] rounded-2xl px-3 py-2 text-sm",
                mine ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-muted rounded-bl-sm",
              )}
            >
              {t.text}
            </p>
          </div>
        );
      })}
      <div ref={bottom} />
    </div>
  );
}

interface ToolEventPayload {
  event: "tool_start" | "tool_end" | "approval_required" | "message_end";
  data: Record<string, unknown>;
}

/** Tool progress, rich cards and approvals relayed by the voice agent on the `nexora.tool` topic. */
function VoiceToolActivity() {
  const { textStreams } = useTextStream(VOICE_PROTOCOL.toolTopic);
  const events = useMemo(() => {
    const parsed: ToolEventPayload[] = [];
    for (const s of textStreams) {
      try {
        parsed.push(JSON.parse(s.text) as ToolEventPayload);
      } catch {
        /* ignore partial or invalid payloads */
      }
    }
    return parsed;
  }, [textStreams]);

  const lastTurnStart = events.map((e) => e.event).lastIndexOf("message_end");
  const current = events.slice(lastTurnStart >= 0 && lastTurnStart === events.length - 1 ? 0 : lastTurnStart + 1);
  const tools: ToolProgress[] = [];
  for (const e of current) {
    if (e.event === "tool_start") tools.push({ id: String(e.data.id), tool: String(e.data.tool), status: "running" });
    if (e.event === "tool_end") {
      const entry: ToolProgress = {
        id: String(e.data.id),
        tool: String(e.data.tool),
        status: e.data.ok ? "ok" : "error",
        message: String(e.data.message ?? ""),
      };
      const i = tools.findIndex((t) => t.id === entry.id);
      if (i >= 0) tools[i] = entry;
      else tools.push(entry);
    }
  }
  const lastCard = [...events].reverse().find((e) => e.event === "tool_end" && e.data.card)?.data.card as
    ResultCard | undefined;
  const approvals = events.filter((e) => e.event === "approval_required").slice(-2);

  if (!tools.length && !lastCard && !approvals.length) return null;
  return (
    <div className="mb-4 max-h-72 scrollbar-thin space-y-2 overflow-y-auto">
      <ToolChips tools={tools} />
      {lastCard && lastCard.type !== "places" && <ResultCardView card={lastCard} />}
      {approvals.map((a) => (
        <ApprovalCard
          key={String(a.data.approval_id)}
          approvalId={String(a.data.approval_id)}
          tool={String(a.data.tool)}
          summary={String(a.data.summary)}
        />
      ))}
    </div>
  );
}

function orbMood(state: OrbState): OrbMood {
  return state === "error" ? "muted" : state;
}

/** Live loudness of Nexora's voice, used to animate the orb while it speaks. */
function useAgentVolume(): number {
  const { audioTrack } = useVoiceAssistant();
  return useTrackVolume(audioTrack);
}

export function VoicePanel() {
  const voice = useVoice();
  const startVoice = useStartVoice();
  const { status, error, panelOpen, micMuted, holdToTalk, pttActive, activation, conversationId, set } =
    useVoiceStore();
  const { orb, label } = useOrbState();
  const volume = useAgentVolume();
  const live = status === "connected" || status === "reconnecting";
  const busy = status !== "idle" && status !== "error";

  if (!panelOpen && !busy) return null;

  if (!panelOpen && busy) {
    return (
      <button
        type="button"
        onClick={() => set({ panelOpen: true })}
        className="glass fixed right-4 bottom-24 z-50 flex items-center gap-2 rounded-full py-1.5 pr-4 pl-1.5 shadow-lg md:bottom-6"
        aria-label="Open voice session"
      >
        <VoiceOrb state={orb} size="sm" />
        <span className="text-sm font-medium">{label}</span>
      </button>
    );
  }

  return (
    <div
      role="dialog"
      aria-label="Voice assistant"
      className="glass-strong gradient-border fixed inset-x-3 bottom-24 z-50 rounded-[2rem] p-5 md:inset-x-auto md:right-6 md:bottom-6 md:w-[420px]"
    >
      <RoomAudioRenderer />
      <div className="mb-2 flex items-center justify-between">
        <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs">
          {live ? (
            <>
              <span className="size-2 animate-pulse rounded-full bg-red-500" />
              {micMuted ? "Mic off" : "Microphone live"} · {activation === "wake_word" ? "Wake word" : "Voice"}
            </>
          ) : (
            <>
              <ShieldCheck className="size-3.5" /> Audio streams only during a session
            </>
          )}
        </span>
        <Button size="icon-sm" variant="ghost" onClick={() => set({ panelOpen: false })} aria-label="Minimise">
          <X />
        </Button>
      </div>

      <div className="flex flex-col items-center py-3">
        <Orb3D mood={orbMood(orb)} level={volume} className="w-52" />
        <p className="mt-5 text-lg font-medium" aria-live="polite">
          {label}
        </p>
        {error && <p className="text-destructive mt-1 max-w-xs text-center text-sm">{error}</p>}
        <StartAudio
          label="Tap to enable audio"
          className="bg-primary text-primary-foreground mt-3 rounded-full px-4 py-1.5 text-sm"
        />
      </div>

      {live && (
        <>
          <VoiceToolActivity />
          <div className="bg-background/60 mb-4 rounded-2xl border p-3">
            <Transcript />
          </div>
        </>
      )}

      <div className="flex items-center justify-center gap-2">
        {status === "idle" || status === "error" ? (
          <>
            <Button onClick={() => void startVoice(conversationId)} size="lg">
              <Mic /> {status === "error" ? "Try again" : "Start talking"}
            </Button>
            <Button variant="ghost" size="lg" onClick={() => set({ panelOpen: false, error: null, status: "idle" })}>
              Close
            </Button>
          </>
        ) : (
          <>
            {holdToTalk ? (
              <Button
                size="lg"
                className={cn("touch-none select-none", pttActive && "ring-brand/40 ring-4")}
                onPointerDown={() => void voice.beginTurn()}
                onPointerUp={() => void voice.endTurn()}
                onPointerLeave={() => pttActive && void voice.endTurn()}
                disabled={!live}
              >
                <Hand /> {pttActive ? "Release to send" : "Hold to talk"}
              </Button>
            ) : (
              <Button
                variant="outline"
                size="icon-lg"
                onClick={() => void voice.toggleMute()}
                disabled={!live}
                aria-label={micMuted ? "Unmute" : "Mute"}
              >
                {micMuted ? <MicOff /> : <Mic />}
              </Button>
            )}
            <Button
              variant="outline"
              size="lg"
              onClick={() => void voice.interrupt()}
              disabled={!live}
              aria-label="Stop speaking"
            >
              <Square /> Stop
            </Button>
            <Button variant="destructive" size="lg" onClick={() => void voice.end()} aria-label="End session">
              <PhoneOff /> End
            </Button>
          </>
        )}
      </div>
      {conversationId && live && (
        <p className="text-muted-foreground mt-3 text-center text-xs">
          Saved to{" "}
          <Link className="underline underline-offset-2" href={`/assistant/${conversationId}`}>
            this conversation
          </Link>
        </p>
      )}
    </div>
  );
}
