import type { Metadata } from "next";

import { LiveScreen } from "@/features/live/components/live-screen";

export const metadata: Metadata = { title: "Live" };

export default function LivePage() {
  return <LiveScreen />;
}
