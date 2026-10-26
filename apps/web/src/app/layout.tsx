import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";

import type { Metadata, Viewport } from "next";

import { Providers } from "@/lib/providers";

export const metadata: Metadata = {
  title: { default: "GPUWatch", template: "%s | GPUWatch" },
  description: "Self-hosted GPU monitoring and cost intelligence: why your GPUs are expensive or slow, and what to do about it.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  // Meta tags cannot read CSS variables: these mirror --background in globals.css.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f6f9" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0d12" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
