import type { Metadata } from "next";
import { Suspense } from "react";

import { InsightsScreen } from "@/features/insights/components/insights-screen";

export const metadata: Metadata = { title: "Insights" };

export default function InsightsPage() {
  return (
    <Suspense>
      <InsightsScreen />
    </Suspense>
  );
}
