import type { Metadata } from "next";
import { Suspense } from "react";

import { HostsScreen } from "@/features/fleet/components/hosts-screen";

export const metadata: Metadata = { title: "Hosts" };

export default function HostsPage() {
  return (
    <Suspense>
      <HostsScreen />
    </Suspense>
  );
}
