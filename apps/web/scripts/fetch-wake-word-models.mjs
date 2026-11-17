#!/usr/bin/env node
/**
 * Downloads openWakeWord's shared feature models into public/wake-word/ (git-ignored):
 *   melspectrogram.onnx, embedding_model.onnx  (needed by every wake word model)
 * With --test, also the pre-trained "Hey Jarvis" model, saved as hey_nexora.onnx, so the pipeline can be tried before
 * a "Hey Nexora" model is trained. Pre-trained openWakeWord models are CC BY-NC-SA 4.0: personal use only.
 *
 * Usage: node scripts/fetch-wake-word-models.mjs [--test] [--force]
 */
import { createWriteStream, existsSync, mkdirSync, renameSync, statSync } from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

const RELEASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1";
const dir = path.join(import.meta.dirname, "..", "public", "wake-word");
const force = process.argv.includes("--force");
const files = [
  { url: `${RELEASE}/melspectrogram.onnx`, name: "melspectrogram.onnx" },
  { url: `${RELEASE}/embedding_model.onnx`, name: "embedding_model.onnx" },
];
if (process.argv.includes("--test"))
  files.push({ url: `${RELEASE}/hey_jarvis_v0.1.onnx`, name: "hey_nexora.onnx", test: true });

mkdirSync(dir, { recursive: true });
for (const file of files) {
  const target = path.join(dir, file.name);
  if (existsSync(target) && !force) {
    console.log(`✓ ${file.name} already present (${statSync(target).size} bytes)`);
    continue;
  }
  const res = await fetch(file.url);
  if (!res.ok || !res.body) throw new Error(`Download failed: ${file.url} (${res.status})`);
  const partial = `${target}.part`;
  await pipeline(Readable.fromWeb(res.body), createWriteStream(partial));
  renameSync(partial, target);
  console.log(`↓ ${file.name} (${statSync(target).size} bytes)${file.test ? '  ← test model: say "Hey Jarvis"' : ""}`);
}
