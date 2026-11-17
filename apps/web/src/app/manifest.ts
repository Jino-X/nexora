import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Nexora - Personal AI Assistant",
    short_name: "Nexora",
    description: "Your personal AI assistant for text and real-time voice, in English and Tamil.",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#16151d",
    theme_color: "#5b3fd6",
    categories: ["productivity", "lifestyle"],
    icons: [
      { src: "/icons/icon.svg", sizes: "any", type: "image/svg+xml" },
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Talk to Nexora", url: "/assistant", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
      { name: "Today's briefing", url: "/dashboard", icons: [{ src: "/icons/icon-192.png", sizes: "192x192" }] },
    ],
  };
}
