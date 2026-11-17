"use client";

/**
 * One LiveKit voice session shared by push-to-talk, the voice orb and the wake word.
 *
 * Flow: POST /voice/sessions (short-lived token + explicit agent dispatch) -> Room.connect ->
 * publish microphone -> the Nexora voice agent joins and runs STT -> assistant graph -> TTS.
 * Interruption: speaking over the agent barges in (agent-side VAD), and the Stop button sends the
 * `nexora.interrupt` RPC. Push-to-talk uses `nexora.start_turn` / `nexora.end_turn` RPCs.
 */

import { RoomContext } from "@livekit/components-react";
import type { VoiceSession } from "@nexora/shared-types";
import { VOICE_PROTOCOL } from "@nexora/shared-types";
import { useQueryClient } from "@tanstack/react-query";
import { DisconnectReason, MediaDeviceFailure, Room, RoomEvent, type RemoteParticipant } from "livekit-client";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api/client";
import { qk } from "@/lib/api/hooks";
import { useVoiceStore } from "@/lib/voice/voice-store";

interface VoiceControls {
  room: Room;
  start: (
    activation: "push_to_talk" | "wake_word",
    opts?: { conversationId?: string | null; holdToTalk?: boolean },
  ) => Promise<void>;
  end: (reason?: string) => Promise<void>;
  toggleMute: () => Promise<void>;
  interrupt: () => Promise<void>;
  beginTurn: () => Promise<void>;
  endTurn: () => Promise<void>;
}

const VoiceContext = createContext<VoiceControls | null>(null);

function agentParticipant(room: Room): RemoteParticipant | undefined {
  return Array.from(room.remoteParticipants.values()).find((p) => p.isAgent);
}

function micErrorMessage(error: unknown): string {
  const failure = MediaDeviceFailure.getFailure(error);
  if (failure === MediaDeviceFailure.PermissionDenied) {
    return "Microphone permission was denied. Allow microphone access in your browser settings.";
  }
  if (failure === MediaDeviceFailure.NotFound) return "No microphone was found.";
  if (failure === MediaDeviceFailure.DeviceInUse) return "Your microphone is in use by another app.";
  return error instanceof Error ? error.message : "Couldn't start the microphone.";
}

export function VoiceProvider({ children }: { children: ReactNode }) {
  const set = useVoiceStore((s) => s.set);
  const qc = useQueryClient();
  const sessionRef = useRef<VoiceSession | null>(null);
  const endingRef = useRef(false);
  const room = useMemo(
    () =>
      new Room({
        adaptiveStream: true,
        dynacast: true,
        audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      }),
    [],
  );

  const end = useCallback(
    async (reason = "user") => {
      if (endingRef.current) return;
      endingRef.current = true;
      const session = sessionRef.current;
      sessionRef.current = null;
      set({ status: "ending" });
      try {
        await room.disconnect(true);
      } finally {
        if (session) {
          await api(`/voice/sessions/${session.session_id}/end`, { method: "POST" }).catch(() => undefined);
          qc.invalidateQueries({ queryKey: qk.conversation(session.conversation_id) });
          qc.invalidateQueries({ queryKey: ["conversations"] });
        }
        set({ status: "idle", sessionId: null, activation: null, pttActive: false, micMuted: false });
        endingRef.current = false;
        if (reason !== "user") toast.message("Voice session ended", { description: reason });
      }
    },
    [qc, room, set],
  );

  useEffect(() => {
    const onDisconnected = (reason?: DisconnectReason) => {
      if (endingRef.current || !sessionRef.current) return;
      const message =
        reason === DisconnectReason.ROOM_DELETED
          ? "The session finished."
          : reason === DisconnectReason.DUPLICATE_IDENTITY
            ? "Voice was opened in another tab."
            : "Connection lost.";
      void end(message);
    };
    const onReconnecting = () => set({ status: "reconnecting" });
    const onReconnected = () => set({ status: "connected" });
    const onMediaError = (error: Error) => set({ error: micErrorMessage(error) });
    room.on(RoomEvent.Disconnected, onDisconnected);
    room.on(RoomEvent.Reconnecting, onReconnecting);
    room.on(RoomEvent.Reconnected, onReconnected);
    room.on(RoomEvent.MediaDevicesError, onMediaError);
    return () => {
      room.off(RoomEvent.Disconnected, onDisconnected);
      room.off(RoomEvent.Reconnecting, onReconnecting);
      room.off(RoomEvent.Reconnected, onReconnected);
      room.off(RoomEvent.MediaDevicesError, onMediaError);
    };
  }, [end, room, set]);

  useEffect(() => {
    const onUnload = () => {
      if (sessionRef.current) void room.disconnect();
    };
    window.addEventListener("pagehide", onUnload);
    return () => window.removeEventListener("pagehide", onUnload);
  }, [room]);

  const start = useCallback<VoiceControls["start"]>(
    async (activation, opts) => {
      const status = useVoiceStore.getState().status;
      if (status !== "idle" && status !== "error") {
        set({ panelOpen: true });
        return;
      }
      // Wake word sessions are always hands-free; push-to-talk can be hold-to-talk (manual turns).
      const holdToTalk = activation === "push_to_talk" && Boolean(opts?.holdToTalk);
      set({ status: "requesting", error: null, activation, panelOpen: true, holdToTalk });
      let session: VoiceSession;
      try {
        session = await api<VoiceSession>("/voice/sessions", {
          method: "POST",
          body: { activation, conversation_id: opts?.conversationId ?? null, hold_to_talk: holdToTalk },
        });
      } catch (error) {
        const message =
          error instanceof ApiError && error.isNotConfigured
            ? "Voice isn't configured on this server yet (LiveKit). Text chat still works."
            : error instanceof Error
              ? error.message
              : "Couldn't start a voice session.";
        set({ status: "error", error: message, activation: null });
        return;
      }
      sessionRef.current = session;
      set({ status: "connecting", sessionId: session.session_id, conversationId: session.conversation_id });
      try {
        await room.connect(session.server_url, session.participant_token, { autoSubscribe: true });
      } catch (error) {
        sessionRef.current = null;
        await api(`/voice/sessions/${session.session_id}/end`, { method: "POST" }).catch(() => undefined);
        set({
          status: "error",
          error: `Couldn't reach the voice server: ${error instanceof Error ? error.message : "unknown error"}`,
        });
        return;
      }
      try {
        await room.localParticipant.setMicrophoneEnabled(!holdToTalk);
        set({ status: "connected", micMuted: holdToTalk });
      } catch (error) {
        set({ status: "error", error: micErrorMessage(error) });
        await end("Microphone unavailable");
      }
    },
    [end, room, set],
  );

  const rpc = useCallback(
    async (method: string) => {
      const agent = agentParticipant(room);
      if (!agent) return;
      try {
        await room.localParticipant.performRpc({
          destinationIdentity: agent.identity,
          method,
          payload: "",
          responseTimeout: 3000,
        });
      } catch {
        /* agent may not support the method yet; audio-level barge-in still works */
      }
    },
    [room],
  );

  const toggleMute = useCallback(async () => {
    const muted = !useVoiceStore.getState().micMuted;
    await room.localParticipant.setMicrophoneEnabled(!muted);
    set({ micMuted: muted });
  }, [room, set]);

  const interrupt = useCallback(() => rpc(VOICE_PROTOCOL.rpcInterrupt), [rpc]);

  const beginTurn = useCallback(async () => {
    set({ pttActive: true });
    await rpc(VOICE_PROTOCOL.rpcStartTurn);
    await room.localParticipant.setMicrophoneEnabled(true);
    set({ micMuted: false });
  }, [room, rpc, set]);

  const endTurn = useCallback(async () => {
    await room.localParticipant.setMicrophoneEnabled(false);
    set({ micMuted: true, pttActive: false });
    await rpc(VOICE_PROTOCOL.rpcEndTurn);
  }, [room, rpc, set]);

  const value = useMemo(
    () => ({ room, start, end, toggleMute, interrupt, beginTurn, endTurn }),
    [room, start, end, toggleMute, interrupt, beginTurn, endTurn],
  );

  return (
    <VoiceContext.Provider value={value}>
      <RoomContext.Provider value={room}>{children}</RoomContext.Provider>
    </VoiceContext.Provider>
  );
}

export function useVoice(): VoiceControls {
  const ctx = useContext(VoiceContext);
  if (!ctx) throw new Error("useVoice must be used inside VoiceProvider");
  return ctx;
}
