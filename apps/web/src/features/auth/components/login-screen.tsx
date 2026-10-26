"use client";

import { ArrowRightIcon, CoinsIcon, EyeIcon, EyeOffIcon, MoonIcon, ThermometerIcon } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { WatchLogo, WatchMark } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FieldError, Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";
import { safeNext } from "@/lib/auth-redirect";

import { useLogin } from "../api";

const PITCH = [
  {
    icon: CoinsIcon,
    title: "Every GPU-hour accounted for",
    body: "Attributed to the workload that held the GPU, or to idle, adding up exactly to your configured rates.",
  },
  {
    icon: MoonIcon,
    title: "Idle spend, found for you",
    body: "Models loaded overnight with no traffic, spare cards, oversized GPUs: ranked by what they cost a month.",
  },
  {
    icon: ThermometerIcon,
    title: "Slow, explained",
    body: "Power caps, thermal limits and memory pressure read from the driver itself, with what to change.",
  },
  {
    icon: EyeIcon,
    title: "Observe only",
    body: "The agent opens no port and runs no commands. GPUWatch recommends; it never touches a workload.",
  },
];

export function LoginScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const login = useLogin();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [show, setShow] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const expired = params.get("reason") === "expired";

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setError(null);
    login.mutate(
      { email: email.trim(), password },
      {
        onSuccess: (session) => {
          toast.success(`Welcome back, ${session.user.name.split(" ")[0]}.`);
          router.replace(safeNext(params.get("next")));
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <div className="grid min-h-dvh bg-background lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <div className="relative flex flex-col px-6 py-6 sm:px-10">
        <div className="flex items-center justify-between">
          <WatchLogo />
          <ThemeToggle />
        </div>
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[360px]">
            <h1 className="text-[26px] leading-tight font-semibold tracking-[-0.025em]">Sign in to GPUWatch</h1>
            <p className="mt-1.5 text-[13.5px] text-muted-foreground">
              Why is my GPU expensive or slow, and what can I do about it?
            </p>
            {expired && (
              <div role="status" className="mt-5 rounded-lg bg-warning-soft px-3.5 py-2.5 text-[13px] text-warning">
                Your session expired. Sign in again to pick up where you left off.
              </div>
            )}
            <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  autoFocus
                  placeholder="you@company.com"
                  className="h-10"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={!!error || undefined}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={show ? "text" : "password"}
                    autoComplete="current-password"
                    className="h-10 pr-10"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    aria-invalid={!!error || undefined}
                  />
                  <button
                    type="button"
                    onClick={() => setShow((s) => !s)}
                    aria-label={show ? "Hide password" : "Show password"}
                    className="absolute top-1/2 right-2 flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
                  >
                    {show ? <EyeOffIcon className="size-4" /> : <EyeIcon className="size-4" />}
                  </button>
                </div>
              </div>
              {error && <FieldError>{error}</FieldError>}
              <Button type="submit" size="lg" className="w-full" disabled={login.isPending}>
                {login.isPending ? "Signing in..." : "Sign in"}
                {!login.isPending && <ArrowRightIcon />}
              </Button>
            </form>
            <p className="mt-6 text-xs leading-relaxed text-muted-foreground">
              Accounts are created by an owner under Users. Forgot your password? Ask an owner to reset it, or run{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px]">gpuwatch create-owner</code> on the server.
            </p>
          </div>
        </div>
        <p className="text-[11.5px] text-faint">Self-hosted. Metrics never leave your infrastructure, and nothing is sent anywhere by default.</p>
      </div>

      <aside className="relative hidden overflow-hidden bg-[var(--panel)] p-10 text-white lg:flex lg:flex-col lg:justify-between">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-90"
          style={{
            background:
              "radial-gradient(60% 50% at 80% 10%, var(--panel-glow), transparent 70%), radial-gradient(50% 45% at 10% 90%, var(--panel-glow-2), transparent 70%)",
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage: "linear-gradient(white 1px, transparent 1px), linear-gradient(90deg, white 1px, transparent 1px)",
            backgroundSize: "36px 36px",
          }}
        />
        <div className="relative flex items-center gap-2 text-[13px] font-medium text-white/70">
          <WatchMark className="size-6" />
          Open-source GPU monitoring
        </div>

        <div className="relative max-w-lg">
          <h2 className="text-[34px] leading-[1.12] font-semibold tracking-[-0.03em]">
            Stop paying for GPUs
            <br />
            <span className="text-[var(--panel-accent)]">that are doing nothing.</span>
          </h2>
          <p className="mt-3 text-[14.5px] leading-relaxed text-white/65">
            A small agent on each machine reads NVIDIA metrics, processes and inference servers. GPUWatch keeps the history,
            puts a price on every hour, and tells you what is wasting money or slowing work down.
          </p>

          <div className="mt-8 rounded-2xl bg-white/[0.06] p-4 shadow-[0_20px_60px_rgba(0,0,0,0.35)] ring-1 ring-white/10 backdrop-blur">
            <div className="flex items-center justify-between text-[12px] text-white/55">
              <span>Example finding, demo fleet</span>
              <span className="rounded-full bg-[var(--panel-accent-soft)] px-2 py-0.5 font-semibold text-[var(--panel-accent)]">
                Idle with a model loaded
              </span>
            </div>
            <div className="mt-3 font-mono text-[12px] leading-relaxed text-white/80">
              GPU 6 on train-node-01 held 31 GiB for a notebook with utilization under 5% overnight and through the
              weekend. <span className="text-[var(--panel-accent)]">Unload it when idle, or move it to a busy GPU.</span>
            </div>
            <div className="mt-3 flex items-center gap-4 text-[11.5px] text-white/50">
              <span>Evidence: idle periods</span>
              <span>Cost: at your rate</span>
              <span>Action: yours</span>
            </div>
          </div>

          <ul className="mt-8 grid gap-5 sm:grid-cols-2">
            {PITCH.map((p) => (
              <li key={p.title} className="flex gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/10 text-[var(--panel-accent)]">
                  <p.icon className="size-4" />
                </span>
                <div>
                  <div className="text-[13px] font-semibold">{p.title}</div>
                  <div className="mt-0.5 text-[12.5px] leading-relaxed text-white/55">{p.body}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative text-[11.5px] text-white/40">MIT licensed. Part of the Euron open-source initiative.</div>
      </aside>
    </div>
  );
}
