"use client";

import { MenuIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { WatchLogo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useSystemInfo } from "@/features/settings/api";
import { cn } from "@/lib/cn";

import { SidebarNav } from "./sidebar";
import { UserMenu } from "./user-menu";

function GatewayStatus() {
  const { data, isError } = useSystemInfo();
  const checks = (data?.checks ?? {}) as Record<string, { ok?: boolean }>;
  const healthy = !isError && !!data && Object.values(checks).every((c) => c?.ok !== false);
  const label = !data && !isError ? "Checking service" : healthy ? "Service healthy" : "Service degraded";
  return (
    <Link
      href="/settings"
      className="hidden items-center gap-2 rounded-full bg-muted px-3 py-1 text-[12px] font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring md:inline-flex"
    >
      <span className="relative flex size-2">
        {healthy && <span className="absolute inline-flex size-full animate-ping rounded-full bg-savings opacity-40" />}
        <span className={cn("relative inline-flex size-2 rounded-full", healthy ? "bg-savings" : data || isError ? "bg-warning" : "bg-faint")} />
      </span>
      {label}
      {data && <span className="text-faint">v{data.version}</span>}
    </Link>
  );
}

export function Topbar() {
  const [menuOpen, setMenuOpen] = React.useState(false);

  return (
    <header className="sticky top-0 z-30 bg-background/80 backdrop-blur-md supports-[backdrop-filter]:bg-background/70">
      <div className="flex h-14 items-center gap-2 px-4 sm:px-6 lg:px-8">
        <Button variant="subtle" size="icon" className="-ml-2 lg:hidden" aria-label="Open navigation" onClick={() => setMenuOpen(true)}>
          <MenuIcon />
        </Button>
        <Link href="/" className="rounded-lg lg:hidden" aria-label="GPUWatch home">
          <WatchLogo />
        </Link>
        <GatewayStatus />
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetContent side="left" className="bg-sidebar">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <div className="flex h-14 items-center px-4">
            <WatchLogo />
          </div>
          <div className="overflow-y-auto px-3 pb-6">
            <SidebarNav onNavigate={() => setMenuOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>
    </header>
  );
}
