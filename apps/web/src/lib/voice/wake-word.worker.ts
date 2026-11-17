/// <reference lib="webworker" />
/**
 * Runs the openWakeWord models off the main thread. Receives raw microphone blocks at the AudioContext's rate,
 * resamples them to 16 kHz and posts a message when the wake word's score reaches the threshold. Nothing leaves the
 * device: the models are fetched from this site and inference runs in WebAssembly.
 */
import * as ort from "onnxruntime-web/wasm";

import {
  EMBEDDING_SIZE,
  EMBEDDING_WINDOW,
  MEL_BINS,
  Resampler,
  toInt16Scale,
  WakeWordPipeline,
  type WakeWordModels,
} from "./wake-word-pipeline";

export type WakeWordWorkerRequest =
  | {
      type: "init";
      melspectrogramUrl: string;
      embeddingUrl: string;
      modelUrl: string;
      threshold: number;
    }
  /** Sent once the microphone is open: the rate its samples arrive at. */
  | { type: "start"; inputSampleRate: number }
  | { type: "audio"; samples: Float32Array }
  | { type: "threshold"; threshold: number };

export type WakeWordWorkerMessage =
  | { type: "ready" }
  | { type: "detected"; score: number }
  | { type: "error"; code: "missing-model" | "load-failed" | "runtime"; message: string };

const scope = self as unknown as DedicatedWorkerGlobalScope;
const post = (message: WakeWordWorkerMessage) => scope.postMessage(message);

// One thread: cross-origin isolation (needed for threads) isn't enabled, and these models are tiny.
ort.env.wasm.numThreads = 1;
ort.env.logLevel = "error";

let pipeline: WakeWordPipeline | null = null;
let resampler: Resampler | null = null;
let threshold = 0.5;
let queue: Promise<void> = Promise.resolve();
/** Chunks still to process; audio is dropped beyond this so a slow device can't fall ever further behind. */
let backlog = 0;
const MAX_BACKLOG = 8;

async function fetchModel(url: string): Promise<Uint8Array> {
  const res = await fetch(url);
  if (res.status === 404) {
    const name = url.split("/").pop();
    throw Object.assign(new Error(`${name} is missing. Add it to public/wake-word/ (see the README there).`), {
      code: "missing-model" as const,
    });
  }
  if (!res.ok) throw new Error(`Couldn't load ${url} (HTTP ${res.status}).`);
  return new Uint8Array(await res.arrayBuffer());
}

async function init(req: Extract<WakeWordWorkerRequest, { type: "init" }>) {
  const [melBytes, embeddingBytes, modelBytes] = await Promise.all([
    fetchModel(req.melspectrogramUrl),
    fetchModel(req.embeddingUrl),
    fetchModel(req.modelUrl),
  ]);
  const options: ort.InferenceSession.SessionOptions = { executionProviders: ["wasm"], graphOptimizationLevel: "all" };
  const [mel, embedding, model] = await Promise.all([
    ort.InferenceSession.create(melBytes, options),
    ort.InferenceSession.create(embeddingBytes, options),
    ort.InferenceSession.create(modelBytes, options),
  ]);

  const first = (out: ort.InferenceSession.OnnxValueMapType, session: ort.InferenceSession) =>
    out[session.outputNames[0]].data as Float32Array;
  const models: WakeWordModels = {
    melspectrogram: async (audio) =>
      first(await mel.run({ [mel.inputNames[0]]: new ort.Tensor("float32", audio, [1, audio.length]) }), mel),
    embedding: async (window) =>
      first(
        await embedding.run({
          [embedding.inputNames[0]]: new ort.Tensor("float32", window, [1, EMBEDDING_WINDOW, MEL_BINS, 1]),
        }),
        embedding,
      ),
    score: async (features) =>
      first(
        await model.run({
          [model.inputNames[0]]: new ort.Tensor("float32", features, [
            1,
            features.length / EMBEDDING_SIZE,
            EMBEDDING_SIZE,
          ]),
        }),
        model,
      )[0],
  };

  pipeline = new WakeWordPipeline(models);
  threshold = req.threshold;
  post({ type: "ready" });
}

function onAudio(samples: Float32Array) {
  const current = pipeline;
  const rate = resampler;
  if (!current || !rate) return;
  if (backlog >= MAX_BACKLOG) return;
  backlog++;
  queue = queue
    .then(async () => {
      const scores = await current.push(toInt16Scale(rate.push(samples)));
      const best = scores.length ? Math.max(...scores) : 0;
      if (best >= threshold) {
        // Start fresh, so the same utterance can't trigger twice.
        current.reset();
        post({ type: "detected", score: best });
      }
    })
    .catch((err: unknown) =>
      post({ type: "error", code: "runtime", message: err instanceof Error ? err.message : String(err) }),
    )
    .finally(() => {
      backlog--;
    });
}

scope.onmessage = (event: MessageEvent<WakeWordWorkerRequest>) => {
  const req = event.data;
  if (req.type === "init") {
    init(req).catch((err: unknown) => {
      const code = (err as { code?: string }).code === "missing-model" ? "missing-model" : "load-failed";
      post({ type: "error", code, message: err instanceof Error ? err.message : String(err) });
    });
  } else if (req.type === "start") {
    resampler = new Resampler(req.inputSampleRate);
    pipeline?.reset();
  } else if (req.type === "audio") {
    onAudio(req.samples);
  } else if (req.type === "threshold") {
    threshold = req.threshold;
  }
};
