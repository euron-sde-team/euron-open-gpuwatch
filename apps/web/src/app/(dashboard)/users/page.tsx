import type { Metadata } from "next";

import { UsersScreen } from "@/features/users/components/users-screen";

export const metadata: Metadata = { title: "Users" };

export default function Page() {
  return <UsersScreen />;
}
