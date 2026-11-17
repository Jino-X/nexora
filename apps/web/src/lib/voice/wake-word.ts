/**
 * On-device wake word ("Hey Nexora") with openWakeWord models in the browser.
 *
 * An AudioWorklet reads the microphone and a Web Worker runs the models with ONNX Runtime Web (WebAssembly).
 * Nothing is uploaded until a detection fires, and only then does the app connect to LiveKit. Needs, in
 * /public/wake-word/ (git-ignored):
 *   - melspectrogram.onnx and embedding_model.onnx: openWakeWord's shared feature models
 *     (`pnpm --filter @nexora/web wake-word:models` downloads them);
 *   - hey_nexora.onnx: a "Hey Nexora" model trained with openWakeWord's free Colab notebook (see docs/voice.md).
 * No account or key is needed. Limits: foreground tabs only. Browsers suspend microphones in background tabs and on
 * locked phones, so a PWA cannot listen continuously.
 */
import { thresholdForSensitivity } from "./wake-word-pipeline";
import type { WakeWordWorkerMessage, WakeWordWorkerRequest } from "./wake-word.worker";

export interface WakeWordEngine {
  stop: () => Promise<void>;
}

export interface WakeWordOptions {
  modelUrl: string;
  melspectrogramUrl: string;
  embeddingUrl: string;
  captureWorkletUrl: string;
  sensitivity: number; // 0..1, higher = more detections, more false triggers
  onDetect: () => void;
  onError: (message: string) => void;
}

/** The wake word model files aren't on the server, so the feature can't run until they're added. */
export class WakeWordModelMissingError extends Error {
  readonly code = "missing-model";
}

/** Cooldown + suppression gate (pure logic; unit tested). */
export class WakeWordGate {
  private lastTrigger = Number.NEGATIVE_INFINITY;
  private suppressed = false;
  private cooldownMs: number;
  private readonly now: () => number;

  constructor(cooldownMs: number, now: () => number = () => Date.now()) {
    this.cooldownMs = cooldownMs;
    this.now = now;
  }

  setCooldown(ms: number) {
    this.cooldownMs = ms;
  }

  setSuppressed(value: boolean) {
    this.suppressed = value;
  }

  /** Returns true if this detection should start a session. */
  accept(): boolean {
    if (this.suppressed) return false;
    const t = this.now();
    if (t - this.lastTrigger < this.cooldownMs) return false;
    this.lastTrigger = t;
    return true;
  }
}

export function clampSensitivity(value: number): number {
  if (!Number.isFinite(value)) return 0.5;
  return Math.min(0.95, Math.max(0.1, value));
}

const MODEL_LOAD_TIMEOUT_MS = 30_000;

export async function startWakeWord(opts: WakeWordOptions): Promise<WakeWordEngine> {
  const worker = new Worker(new URL("./wake-word.worker.ts", import.meta.url), {
    type: "module",
    name: "nexora-wake-word",
  });
  const send = (message: WakeWordWorkerRequest, transfer: Transferable[] = []) => worker.postMessage(message, transfer);
  let stream: MediaStream | null = null;
  let ctx: AudioContext | null = null;
  let resumeOnGesture: (() => void) | null = null;
  let stopped = false;

  const stop = async () => {
    if (stopped) return;
    stopped = true;
    if (resumeOnGesture) {
      document.removeEventListener("pointerdown", resumeOnGesture);
      document.removeEventListener("keydown", resumeOnGesture);
    }
    stream?.getTracks().forEach((t) => t.stop());
    await ctx?.close().catch(() => undefined);
    worker.terminate();
  };

  try {
    // 1. Load the models first, so a missing model never triggers a microphone prompt.
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("The wake word models took too long to load.")),
        MODEL_LOAD_TIMEOUT_MS,
      );
      worker.onmessage = (event: MessageEvent<WakeWordWorkerMessage>) => {
        const msg = event.data;
        if (msg.type === "ready") {
          clearTimeout(timer);
          resolve();
        } else if (msg.type === "error") {
          clearTimeout(timer);
          reject(msg.code === "missing-model" ? new WakeWordModelMissingError(msg.message) : new Error(msg.message));
        }
      };
      worker.onerror = (event) => {
        clearTimeout(timer);
        reject(new Error(event.message || "The wake word worker failed to start."));
      };
      send({
        type: "init",
        melspectrogramUrl: opts.melspectrogramUrl,
        embeddingUrl: opts.embeddingUrl,
        modelUrl: opts.modelUrl,
        threshold: thresholdForSensitivity(clampSensitivity(opts.sensitivity)),
      });
    });
    if (stopped) return { stop };

    // 2. Open the microphone and stream it to the worker.
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
    ctx = openContext();
    let source: MediaStreamAudioSourceNode;
    try {
      source = ctx.createMediaStreamSource(stream);
    } catch {
      // Firefox can't feed a microphone into a context at a different rate: use the device rate and resample.
      await ctx.close();
      ctx = new AudioContext();
      source = ctx.createMediaStreamSource(stream);
    }
    await ctx.audioWorklet.addModule(opts.captureWorkletUrl);
    const capture = new AudioWorkletNode(ctx, "nexora-wake-word-capture", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      channelCount: 1,
      channelCountMode: "explicit",
    });
    // Silent output keeps the node running in every browser without playing the microphone back.
    const silence = ctx.createGain();
    silence.gain.value = 0;
    source.connect(capture).connect(silence).connect(ctx.destination);

    send({ type: "start", inputSampleRate: ctx.sampleRate });
    capture.port.onmessage = (event: MessageEvent<Float32Array>) => {
      if (!stopped) send({ type: "audio", samples: event.data }, [event.data.buffer]);
    };
    worker.onmessage = (event: MessageEvent<WakeWordWorkerMessage>) => {
      const msg = event.data;
      if (stopped) return;
      if (msg.type === "detected") opts.onDetect();
      else if (msg.type === "error") opts.onError(msg.message);
    };

    // Browsers may start audio suspended until the user interacts with the page; resume on the first interaction.
    if (ctx.state === "suspended") {
      await ctx.resume().catch(() => undefined);
      if (ctx.state === "suspended") {
        const current = ctx;
        resumeOnGesture = () => {
          void current.resume();
          if (resumeOnGesture) {
            document.removeEventListener("pointerdown", resumeOnGesture);
            document.removeEventListener("keydown", resumeOnGesture);
          }
        };
        document.addEventListener("pointerdown", resumeOnGesture);
        document.addEventListener("keydown", resumeOnGesture);
      }
    }
    return { stop };
  } catch (err) {
    await stop();
    if (err instanceof DOMException && err.name === "NotAllowedError") {
      throw new Error("Microphone permission was denied. Allow it in the browser to use the wake word.");
    }
    throw err;
  }
}

/** A 16 kHz context when the browser allows it (no resampling needed), otherwise the device rate. */
function openContext(): AudioContext {
  try {
    return new AudioContext({ sampleRate: 16_000 });
  } catch {
    return new AudioContext();
  }
}

/** Short confirmation chime (WebAudio), so the user knows the mic is about to stream. */
export function playChime() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(660, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(990, ctx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.26);
    osc.onended = () => void ctx.close();
  } catch {
    /* audio not available */
  }
}
