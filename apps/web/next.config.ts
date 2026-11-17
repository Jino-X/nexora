import path from "node:path";

import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const livekitUrl = process.env.NEXT_PUBLIC_LIVEKIT_URL ?? "wss://*.livekit.cloud";
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

/**
 * Security headers. The CSP allows only what the app needs: the Nexora API, Supabase, LiveKit
 * (WebSocket + TURN over HTTPS), OSM tiles for maps, official YouTube/Spotify embeds, and Apple
 * preview audio. 'wasm-unsafe-eval' is required by the on-device wake word engine (ONNX Runtime Web), whose models
 * and worklet are served from this site.
 */
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  `connect-src 'self' ${apiUrl} ${supabaseUrl} ${livekitUrl} https://*.livekit.cloud wss://*.livekit.cloud`,
  "media-src 'self' blob: https://*.itunes.apple.com https://*.mzstatic.com https://audio-ssl.itunes.apple.com",
  "frame-src https://www.youtube-nocookie.com https://open.spotify.com",
  "worker-src 'self' blob:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
]
  .join("; ")
  .replace(/\s+/g, " ");

const nextConfig: NextConfig = {
  // Docker builds set NEXT_OUTPUT=standalone; Vercel ignores it.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  cacheComponents: true,
  partialPrefetching: true,
  transpilePackages: ["@nexora/shared-types"],
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "microphone=(self), geolocation=(self), camera=()" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
    ];
  },
};

export default nextConfig;
