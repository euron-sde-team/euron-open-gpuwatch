import type { Metadata } from "next";
import { Suspense } from "react";

import { CostsScreen } from "@/features/costs/components/costs-screen";

export const metadata: Metadata = { title: "Costs" };

export default function Page() {
  return (
    <Suspense>
      <CostsScreen />
    </Suspense>
  );
}
