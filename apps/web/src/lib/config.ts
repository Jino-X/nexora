/** Public (browser-safe) configuration. Never put secrets in NEXT_PUBLIC_* variables. */

export const config = {
  apiUrl: (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabaseKey: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "",
  appUrl: (process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000").replace(/\/$/, ""),
  wakeWord: {
    // openWakeWord models, served from /public/wake-word/ (git-ignored). No account or key is needed.
    modelPath: process.env.NEXT_PUBLIC_WAKE_WORD_MODEL_URL ?? "/wake-word/hey_nexora.onnx",
    melspectrogramPath: "/wake-word/melspectrogram.onnx",
    embeddingPath: "/wake-word/embedding_model.onnx",
    captureWorkletPath: "/audio/wake-word-capture.js",
    label: "Hey Nexora",
  },
} as const;

export const authMode: "supabase" | "dev" = config.supabaseUrl && config.supabaseKey ? "supabase" : "dev";

/**
 * Whether this deployment offers the wake word. It's off only when NEXT_PUBLIC_WAKE_WORD_MODEL_URL is set empty;
 * missing model files are reported when the engine starts (the wake word status becomes "unconfigured").
 */
export const wakeWordConfigured = Boolean(config.wakeWord.modelPath);

export const DEV_TOKEN_COOKIE = "nexora_dev_token";

export const PUBLIC_ROUTES = ["/login", "/signup", "/forgot-password", "/auth/callback", "/offline"];
