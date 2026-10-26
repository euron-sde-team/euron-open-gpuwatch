import type { Metadata } from "next";

import { SettingsScreen } from "@/features/settings/components/settings-screen";

export const metadata: Metadata = { title: "Settings" };

export default function Page() {
  return <SettingsScreen />;
}
