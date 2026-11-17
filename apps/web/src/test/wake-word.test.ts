import { describe, expect, it } from "vitest";

import { decodeJwtPayload } from "@/lib/auth/dev-auth";
import { clampSensitivity, WakeWordGate } from "@/lib/voice/wake-word";
import {
  CHUNK_SAMPLES,
  EMBEDDING_SIZE,
  EMBEDDING_WINDOW,
  MEL_BINS,
  Resampler,
  thresholdForSensitivity,
  toInt16Scale,
  WakeWordPipeline,
  type WakeWordModels,
} from "@/lib/voice/wake-word-pipeline";

describe("wake word audio helpers", () => {
  it("maps sensitivity to a score threshold, 0.5 being openWakeWord's default", () => {
    expect(thresholdForSensitivity(0.5)).toBe(0.5);
    expect(thresholdForSensitivity(0.6)).toBeCloseTo(0.4);
    expect(thresholdForSensitivity(2)).toBe(0.05);
    expect(thresholdForSensitivity(Number.NaN)).toBe(0.5);
  });

  it("scales Web Audio floats to clipped 16-bit PCM values", () => {
    expect(Array.from(toInt16Scale(Float32Array.from([0, 0.5, -1, 1.5, -2])))).toEqual([
      0, 16384, -32767, 32767, -32768,
    ]);
  });

  it("resamples 48 kHz to 16 kHz in any block size, keeping the tone", () => {
    const tone = Float32Array.from({ length: 48_000 }, (_, i) => Math.sin((2 * Math.PI * 440 * i) / 48_000));
    const resampler = new Resampler(48_000);
    const parts: Float32Array[] = [];
    for (let i = 0; i < tone.length; i += 1000) parts.push(resampler.push(tone.subarray(i, i + 1000)));
    const out = Float32Array.from(parts.flatMap((p) => Array.from(p)));
    expect(Math.abs(out.length - 16_000)).toBeLessThanOrEqual(1);
    // 440 Hz → 880 zero crossings per second, whatever the rate.
    let crossings = 0;
    for (let i = 1; i < out.length; i++) if (out[i - 1] < 0 !== out[i] < 0) crossings++;
    expect(Math.abs(crossings - 880)).toBeLessThanOrEqual(4);
  });

  it("passes 16 kHz audio through unchanged", () => {
    const input = Float32Array.from([0.1, 0.2, 0.3]);
    expect(Array.from(new Resampler(16_000).push(input))).toEqual(Array.from(input));
  });
});

describe("WakeWordPipeline", () => {
  function fakeModels() {
    const calls = { mel: [] as number[], embeddingFirst: [] as number[], scoreLengths: [] as number[] };
    const models: WakeWordModels = {
      // 8 mel frames per call, each frame filled with the call number, so the window's contents can be checked.
      melspectrogram: async (audio) => {
        calls.mel.push(audio.length);
        return new Float32Array(8 * MEL_BINS).fill(calls.mel.length * 10);
      },
      embedding: async (window) => {
        expect(window.length).toBe(EMBEDDING_WINDOW * MEL_BINS);
        calls.embeddingFirst.push(window[window.length - 1]);
        return new Float32Array(EMBEDDING_SIZE).fill(calls.embeddingFirst.length);
      },
      score: async (features) => {
        calls.scoreLengths.push(features.length);
        return features[features.length - 1] / 100;
      },
    };
    return { models, calls };
  }

  it("works in 80 ms chunks, adds 480 samples of left context, and scores once 16 embeddings exist", async () => {
    const { models, calls } = fakeModels();
    const pipeline = new WakeWordPipeline(models);
    expect(await pipeline.push(new Float32Array(1000))).toEqual([]);
    expect(calls.mel).toEqual([]);

    const scores: number[] = [];
    for (let i = 0; i < 20; i++) scores.push(...(await pipeline.push(new Float32Array(CHUNK_SAMPLES))));
    // 1000 + 20 × 1280 samples = 20 whole chunks.
    expect(calls.mel.length).toBe(20);
    expect(calls.mel[0]).toBe(CHUNK_SAMPLES);
    expect(calls.mel.slice(1).every((n) => n === CHUNK_SAMPLES + 480)).toBe(true);
    // The first 15 chunks only build history; then one score per chunk, each over 16 × 96 values.
    expect(scores).toHaveLength(5);
    expect(calls.scoreLengths.every((n) => n === 16 * EMBEDDING_SIZE)).toBe(true);
    expect(scores[0]).toBeCloseTo(16 / 100);
    // New mel frames are scaled x / 10 + 2: call 1 filled 10 → 3.
    expect(calls.embeddingFirst[0]).toBe(3);
  });

  it("starts over after reset", async () => {
    const { models, calls } = fakeModels();
    const pipeline = new WakeWordPipeline(models);
    await pipeline.push(new Float32Array(CHUNK_SAMPLES * 3));
    pipeline.reset();
    await pipeline.push(new Float32Array(CHUNK_SAMPLES));
    expect(calls.mel[calls.mel.length - 1]).toBe(CHUNK_SAMPLES);
  });
});

describe("WakeWordGate", () => {
  it("enforces the cooldown between triggers", () => {
    let now = 10_000;
    const gate = new WakeWordGate(4000, () => now);
    expect(gate.accept()).toBe(true);
    now += 1000;
    expect(gate.accept()).toBe(false);
    now += 3001;
    expect(gate.accept()).toBe(true);
  });

  it("ignores detections while suppressed (voice session active)", () => {
    const gate = new WakeWordGate(0, () => 0);
    gate.setSuppressed(true);
    expect(gate.accept()).toBe(false);
    gate.setSuppressed(false);
    expect(gate.accept()).toBe(true);
  });

  it("clamps sensitivity to a sane range", () => {
    expect(clampSensitivity(2)).toBe(0.95);
    expect(clampSensitivity(-1)).toBe(0.1);
    expect(clampSensitivity(Number.NaN)).toBe(0.5);
  });
});

describe("decodeJwtPayload", () => {
  it("decodes base64url payloads and rejects garbage", () => {
    const payload = btoa(JSON.stringify({ sub: "u1", exp: 123 }))
      .replace(/=+$/, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");
    expect(decodeJwtPayload(`x.${payload}.y`)).toEqual({ sub: "u1", exp: 123 });
    expect(decodeJwtPayload("not-a-jwt")).toBeNull();
  });
});
