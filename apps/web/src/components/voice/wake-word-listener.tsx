"use client";

import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { useMe } from "@/lib/api/hooks";
import { config, wakeWordConfigured } from "@/lib/config";
import { useVoice } from "@/lib/voice/voice-provider";
import { useVoiceStore } from "@/lib/voice/voice-store";
import {
  playChime,
  startWakeWord,
  WakeWordGate,
  WakeWordModelMissingError,
  type WakeWordEngine,
} from "@/lib/voice/wake-word";

/**
 * Runs the on-device wake word engine while: the user enabled it, it's configured, the tab is
 * visible, and no voice session is active. It releases the mic during sessions and in background
 * tabs, so the browser's mic indicator only shows while Nexora is actually listening.
 */
export function WakeWordListener() {
  const me = useMe();
  const voice = useVoice();
  const status = useVoiceStore((s) => s.status);
  const set = useVoiceStore((s) => s.set);
  const engine = useRef<WakeWordEngine | null>(null);
  const gate = useRef(new WakeWordGate(4000));
  const prefs = me.data?.preferences;
  const enabled = Boolean(prefs?.wake_word_enabled);
  const sessionActive = status !== "idle" && status !== "error";

  useEffect(() => {
    gate.current.setCooldown((prefs?.wake_word_cooldown_seconds ?? 4) * 1000);
  }, [prefs?.wake_word_cooldown_seconds]);

  useEffect(() => {
    if (!enabled) {
      set({ wakeWord: "off" });
      return;
    }
    if (!wakeWordConfigured) {
      set({ wakeWord: "unconfigured" });
      return;
    }
    let cancelled = false;

    const stop = async () => {
      const current = engine.current;
      engine.current = null;
      await current?.stop().catch(() => undefined);
    };

    const startIfAllowed = async () => {
      if (cancelled || engine.current || document.visibilityState !== "visible" || sessionActive) {
        if (sessionActive || document.visibilityState !== "visible") set({ wakeWord: "paused" });
        return;
      }
      set({ wakeWord: "starting", wakeWordError: null });
      try {
        const started = await startWakeWord({
          modelUrl: config.wakeWord.modelPath,
          melspectrogramUrl: config.wakeWord.melspectrogramPath,
          embeddingUrl: config.wakeWord.embeddingPath,
          captureWorkletUrl: config.wakeWord.captureWorkletPath,
          sensitivity: prefs?.wake_word_sensitivity ?? 0.6,
          onDetect: () => {
            if (!gate.current.accept()) return;
            playChime();
            void stop().then(() => voice.start("wake_word"));
          },
          onError: (message) => set({ wakeWord: "error", wakeWordError: message }),
        });
        if (cancelled) {
          await started.stop();
          return;
        }
        engine.current = started;
        set({ wakeWord: "listening" });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Wake word failed to start";
        if (err instanceof WakeWordModelMissingError) {
          // A setup gap, not a failure: the header and Settings explain it, so no toast on every page load.
          set({ wakeWord: "unconfigured", wakeWordError: message });
          return;
        }
        set({ wakeWord: "error", wakeWordError: message });
        toast.error("Wake word unavailable", { description: message });
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") void startIfAllowed();
      else {
        void stop();
        set({ wakeWord: "paused" });
      }
    };

    gate.current.setSuppressed(sessionActive);
    if (sessionActive) void stop().then(() => set({ wakeWord: "paused" }));
    else void startIfAllowed();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      void stop();
    };
  }, [enabled, sessionActive, prefs?.wake_word_sensitivity, set, voice]);

  return null;
}
