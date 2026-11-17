import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Noto_Sans_Tamil, Sora } from "next/font/google";

import { Providers } from "@/components/providers";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const notoTamil = Noto_Sans_Tamil({ variable: "--font-tamil", subsets: ["tamil"], weight: ["400", "500", "600"] });
const sora = Sora({ variable: "--font-display", subsets: ["latin"], weight: ["500", "600", "700"] });

export const metadata: Metadata = {
  title: { default: "Nexora", template: "%s · Nexora" },
  description: "Your personal AI assistant for text and real-time voice, in English and Tamil.",
  applicationName: "Nexora",
  appleWebApp: { capable: true, title: "Nexora", statusBarStyle: "black-translucent" },
  formatDetection: { telephone: false },
  icons: { icon: "/icons/icon.svg", apple: "/icons/icon-192.png" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f2fb" },
    { media: "(prefers-color-scheme: dark)", color: "#100d1f" },
  ],
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${notoTamil.variable} ${sora.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
