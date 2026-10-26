import type { Metadata } from "next";
import { Suspense } from "react";

import { InferenceScreen } from "@/features/inference/components/inference-screen";

export const metadata: Metadata = { title: "Inference" };

export default function Page() {
  return (
    <Suspense>
      <InferenceScreen />
    </Suspense>
  );
}
