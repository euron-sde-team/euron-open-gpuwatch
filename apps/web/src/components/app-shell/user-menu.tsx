"use client";

import { KeyRoundIcon, LogOutIcon, SettingsIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Chip } from "@/components/ui/chip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLogout, useMe } from "@/features/auth/api";
import { ChangePasswordDialog } from "@/features/auth/components/change-password-dialog";
import { errorMessage } from "@/lib/api/errors";
import { initials } from "@/lib/format";
import { roleLabel } from "@/lib/roles";

export function UserMenu() {
  const { data: user } = useMe();
  const logout = useLogout();
  const router = useRouter();
  const [pwOpen, setPwOpen] = React.useState(false);

  function signOut() {
    logout.mutate(undefined, {
      onSuccess: () => {
        toast.success("Signed out.");
        router.replace("/login");
      },
      // The session cookie is still valid, so say so instead of pretending.
      onError: (e) => toast.error(errorMessage(e)),
    });
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label="Account menu"
          className="flex size-9 items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-[var(--chart-mem)] to-[var(--primary)] text-[12px] font-semibold text-primary-foreground">
            {initials(user?.name)}
          </span>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="w-60">
          <DropdownMenuLabel className="pb-2">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-[13px] font-semibold text-foreground">{user?.name ?? "Signed in"}</span>
              {user && <Chip tone="primary">{roleLabel(user.role)}</Chip>}
            </div>
            <div className="truncate text-xs">{user?.email}</div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setPwOpen(true)}>
            <KeyRoundIcon />
            Change password
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => router.push("/settings")}>
            <SettingsIcon />
            Settings
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" disabled={logout.isPending} onClick={signOut}>
            <LogOutIcon />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ChangePasswordDialog open={pwOpen} onOpenChange={setPwOpen} />
    </>
  );
}
