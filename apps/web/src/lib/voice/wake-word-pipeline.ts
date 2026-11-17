/**
 * openWakeWord's streaming feature pipeline, ported from its Python `AudioFeatures` class so a model trained with
 * openWakeWord scores the same in the browser. Pure logic with the three models injected, so it is unit tested
 * without ONNX Runtime.
 *
 * Per 80 ms chunk (1,280 samples at 16 kHz):
 *   1. mel spectrogram over the chunk plus 480 samples of left context, scaled `x / 10 + 2`, 32 bins per frame;
 *   2. one 96-value embedding from the last 76 mel frames;
 *   3. the wake word model scores the last 16 embeddings (about 1.3 s of audio) between 0 and 1.
 * Audio goes in as 16-bit PCM values held in floats (-32768..32767), as openWakeWord expects.
 */

export const SAMPLE_RATE = 16_000;
export const CHUNK_SAMPLES = 1280;
const MEL_CONTEXT_SAMPLES = 160 * 3;
export const MEL_BINS = 32;
export const EMBEDDING_WINDOW = 76;
export const EMBEDDING_SIZE = 96;
export const DEFAULT_FEATURE_FRAMES = 16;

export interface WakeWordModels {
  /** Raw 16 kHz int16-scaled audio → mel frames, `frames × 32` values, before the `/10 + 2` scaling. */
  melspectrogram: (audio: Float32Array) => Promise<Float32Array>;
  /** `76 × 32` mel values → 96 embedding values. */
  embedding: (melWindow: Float32Array) => Promise<Float32Array>;
  /** `frames × 96` embedding values → the wake word score, 0..1. */
  score: (features: Float32Array) => Promise<number>;
}

/** Turns the 0..1 sensitivity slider into a score threshold: 0.5 sensitivity is openWakeWord's 0.5 default. */
export function thresholdForSensitivity(sensitivity: number): number {
  const s = Number.isFinite(sensitivity) ? sensitivity : 0.5;
  return Math.min(0.95, Math.max(0.05, 1 - s));
}

/** Web Audio floats (-1..1) → 16-bit PCM values held in floats, clipped. */
export function toInt16Scale(samples: Float32Array): Float32Array {
  const out = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const v = Math.round(samples[i] * 32767);
    out[i] = v > 32767 ? 32767 : v < -32768 ? -32768 : v;
  }
  return out;
}

/**
 * Streaming resampler to 16 kHz: a box low-pass as wide as the rate ratio (to keep speech-band aliasing down), then
 * linear interpolation. Plenty for wake word detection, and cheap enough to run on every audio block.
 */
export class Resampler {
  readonly inputRate: number;
  readonly outputRate: number;
  private readonly ratio: number;
  private readonly box: number;
  private readonly history: Float32Array;
  private historyPos = 0;
  private historySum = 0;
  private last = 0;
  private pos = 1;

  constructor(inputRate: number, outputRate: number = SAMPLE_RATE) {
    this.inputRate = inputRate;
    this.outputRate = outputRate;
    this.ratio = inputRate / outputRate;
    this.box = Math.max(1, Math.round(this.ratio));
    this.history = new Float32Array(this.box);
  }

  push(input: Float32Array): Float32Array {
    if (this.ratio === 1) return input.slice();
    // Low-pass: running mean over the last `box` input samples.
    const filtered = new Float32Array(input.length + 1);
    filtered[0] = this.last;
    for (let i = 0; i < input.length; i++) {
      this.historySum += input[i] - this.history[this.historyPos];
      this.history[this.historyPos] = input[i];
      this.historyPos = (this.historyPos + 1) % this.box;
      filtered[i + 1] = this.historySum / this.box;
    }
    // Linear interpolation; `pos` is measured in `filtered`, whose index 0 is the previous block's last sample.
    const out: number[] = [];
    let t = this.pos;
    while (t <= filtered.length - 1) {
      const i = Math.floor(t);
      const f = t - i;
      out.push(i + 1 < filtered.length ? filtered[i] * (1 - f) + filtered[i + 1] * f : filtered[i]);
      t += this.ratio;
    }
    this.pos = t - (filtered.length - 1);
    this.last = filtered[filtered.length - 1];
    return Float32Array.from(out);
  }
}

export class WakeWordPipeline {
  private pending = new Float32Array(0);
  /** The last 480 samples before the chunk being processed (empty at the start, as in openWakeWord). */
  private context = new Float32Array(0);
  /** Rolling mel frames, `EMBEDDING_WINDOW × 32`, starting as ones like openWakeWord's buffer. */
  private mel = new Float32Array(EMBEDDING_WINDOW * MEL_BINS).fill(1);
  private features: Float32Array[] = [];
  private readonly models: WakeWordModels;
  private readonly featureFrames: number;

  constructor(models: WakeWordModels, featureFrames: number = DEFAULT_FEATURE_FRAMES) {
    this.models = models;
    this.featureFrames = featureFrames;
  }

  /** Feeds 16 kHz int16-scaled audio. Returns one score per completed 80 ms chunk once there's enough history. */
  async push(audio: Float32Array): Promise<number[]> {
    const joined = new Float32Array(this.pending.length + audio.length);
    joined.set(this.pending);
    joined.set(audio, this.pending.length);
    const scores: number[] = [];
    let offset = 0;
    for (; offset + CHUNK_SAMPLES <= joined.length; offset += CHUNK_SAMPLES) {
      const score = await this.processChunk(joined.subarray(offset, offset + CHUNK_SAMPLES));
      if (score !== null) scores.push(score);
    }
    this.pending = joined.slice(offset);
    return scores;
  }

  /** Forget everything heard so far, for example after a detection. */
  reset() {
    this.pending = new Float32Array(0);
    this.context = new Float32Array(0);
    this.mel.fill(1);
    this.features = [];
  }

  private async processChunk(chunk: Float32Array): Promise<number | null> {
    const input = new Float32Array(this.context.length + chunk.length);
    input.set(this.context);
    input.set(chunk, this.context.length);
    this.context = input.slice(Math.max(0, input.length - MEL_CONTEXT_SAMPLES));

    const frames = await this.models.melspectrogram(input);
    const count = Math.floor(frames.length / MEL_BINS);
    if (count > 0) {
      // Shift the window left by `count` frames and append the new ones, scaled like openWakeWord.
      const keep = Math.max(0, EMBEDDING_WINDOW - count);
      this.mel.copyWithin(0, (EMBEDDING_WINDOW - keep) * MEL_BINS);
      const fresh = frames.subarray(Math.max(0, count - EMBEDDING_WINDOW) * MEL_BINS);
      for (let i = 0; i < fresh.length; i++) this.mel[keep * MEL_BINS + i] = fresh[i] / 10 + 2;
    }

    this.features.push(await this.models.embedding(this.mel.slice()));
    if (this.features.length > this.featureFrames) this.features.shift();
    if (this.features.length < this.featureFrames) return null;

    const flat = new Float32Array(this.featureFrames * EMBEDDING_SIZE);
    this.features.forEach((f, i) => flat.set(f.subarray(0, EMBEDDING_SIZE), i * EMBEDDING_SIZE));
    return this.models.score(flat);
  }
}
