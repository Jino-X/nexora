"use client";

import { create } from "zustand";

export type VoiceStatus = "idle" | "requesting" | "connecting" | "connected" | "reconnecting" | "ending" | "error";
export type WakeWordStatus = "off" | "unconfigured" | "starting" | "listening" | "paused" | "error";

interface VoiceUIState {
  status: VoiceStatus;
  error: string | null;
  sessionId: string | null;
  conversationId: string | null;
  activation: "push_to_talk" | "wake_word" | null;
  panelOpen: boolean;
  micMuted: boolean;
  holdToTalk: boolean;
  pttActive: boolean;
  wakeWord: WakeWordStatus;
  wakeWordError: string | null;
  set: (patch: Partial<Omit<VoiceUIState, "set">>) => void;
}

/** Global voice UI state (session lifecycle, mic, wake word) shared across pages. */
export const useVoiceStore = create<VoiceUIState>((set) => ({
  status: "idle",
  error: null,
  sessionId: null,
  conversationId: null,
  activation: null,
  panelOpen: false,
  micMuted: false,
  holdToTalk: false,
  pttActive: false,
  wakeWord: "off",
  wakeWordError: null,
  set: (patch) => set(patch),
}));
