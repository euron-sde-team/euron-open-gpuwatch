import type { Metadata } from "next";

import { GpuScreen } from "@/features/fleet/components/gpu-screen";

export const metadata: Metadata = { title: "GPU" };

export default async function GpuPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <GpuScreen id={id} />;
}
