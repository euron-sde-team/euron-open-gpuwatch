"use client";

import { CheckCircle2Icon, TriangleAlertIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { CodeBlock } from "@/components/code-block";
import { CopyButton } from "@/components/copy-button";
import { Hint } from "@/components/hint";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { errorMessage } from "@/lib/api/errors";
import type { EnrolmentTokenCreated } from "@/lib/api/types";

import { useCreateEnrolmentToken } from "../api";

export function installCommands(origin: string, token: string): { id: string; label: string; code: string }[] {
  return [
    {
      id: "docker",
      label: "Docker",
      code: [
        "# On the GPU machine (needs the NVIDIA Container Toolkit), from a GPUWatch checkout:",
        "docker build -f infra/docker/agent.Dockerfile -t gpuwatch-agent apps/agent",
        "docker run -d --name gpuwatch-agent --restart unless-stopped \\",
        "  --gpus all --pid=host \\",
        `  -e GPUWATCH_URL=${origin} \\`,
        `  -e GPUWATCH_ENROLMENT_TOKEN=${token} \\`,
        "  -v gpuwatch-agent:/var/lib/gpuwatch-agent \\",
        "  gpuwatch-agent run",
      ].join("\n"),
    },
    {
      id: "pip",
      label: "Python",
      code: [
        "# Python 3.10+ on the GPU machine, from a GPUWatch checkout:",
        "pip install ./apps/agent",
        "gpuwatch-agent check        # prints what it finds, sends nothing",
        `GPUWATCH_URL=${origin} \\`,
        `GPUWATCH_ENROLMENT_TOKEN=${token} \\`,
        "GPUWATCH_STATE_DIR=$HOME/.gpuwatch-agent \\",
        "gpuwatch-agent run",
      ].join("\n"),
    },
    {
      id: "dcgm",
      label: "DCGM exporter",
      code: [
        "# Already running NVIDIA DCGM exporter? Read it instead of NVML:",
        "docker run -d --name gpuwatch-agent --restart unless-stopped \\",
        `  -e GPUWATCH_URL=${origin} \\`,
        `  -e GPUWATCH_ENROLMENT_TOKEN=${token} \\`,
        "  -e GPUWATCH_COLLECTOR=dcgm \\",
        "  -e GPUWATCH_DCGM_URL=http://dcgm-exporter:9400/metrics \\",
        "  -v gpuwatch-agent:/var/lib/gpuwatch-agent \\",
        "  gpuwatch-agent run",
      ].join("\n"),
    },
  ];
}

function Revealed({ created }: { created: EnrolmentTokenCreated }) {
  const [origin, setOrigin] = React.useState("");
  React.useEffect(() => setOrigin(window.location.origin), []);
  return (
    <div className="space-y-4">
      <div className="flex gap-3 rounded-xl bg-warning-soft px-4 py-3 text-[13px]">
        <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-warning" />
        <p className="text-foreground">
          Copy this token now. It is shown <strong>once</strong>. Every agent started with it enrols itself and gets its own host token.
        </p>
      </div>
      <div className="flex items-center gap-2 rounded-xl bg-muted p-1.5 pl-3.5">
        <code className="min-w-0 flex-1 truncate font-mono text-[12.5px] select-all" data-testid="enrolment-token">
          {created.token}
        </code>
        <CopyButton value={created.token} label="Copy token" variant="default" />
      </div>
      <CodeBlock samples={installCommands(origin, created.token)} />
      <p className="text-[12.5px] leading-relaxed text-muted-foreground">
        The host appears in the list within seconds of the agent starting. The agent only sends: it opens no port and runs no
        commands from GPUWatch. Add <code className="font-mono">--pid=host</code> so process names resolve.
      </p>
    </div>
  );
}

const EXPIRY = [
  { value: "1", label: "1 day" },
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "365", label: "1 year" },
];

/** Create an enrolment token and show the install commands that use it. */
export function AddHostDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const create = useCreateEnrolmentToken();
  const [name, setName] = React.useState("");
  const [labels, setLabels] = React.useState("");
  const [days, setDays] = React.useState("7");
  const [maxUses, setMaxUses] = React.useState("");
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [serverError, setServerError] = React.useState<string | null>(null);
  const [created, setCreated] = React.useState<EnrolmentTokenCreated | null>(null);

  React.useEffect(() => {
    if (open) {
      setName("");
      setLabels("");
      setDays("7");
      setMaxUses("");
      setErrors({});
      setServerError(null);
      setCreated(null);
    }
  }, [open]);

  function parseLabels(raw: string): Record<string, string> | null {
    const out: Record<string, string> = {};
    for (const part of raw.split(",").map((p) => p.trim()).filter(Boolean)) {
      const [k, ...v] = part.split("=");
      if (!k || !/^[A-Za-z0-9_.-]+$/.test(k.trim())) return null;
      out[k.trim()] = v.join("=").trim();
    }
    return out;
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = 'Name it after the machines it enrols, for example "training nodes".';
    const parsed = parseLabels(labels);
    if (parsed === null) errs.labels = "Use key=value pairs separated by commas, for example env=prod,team=ml.";
    const uses = maxUses.trim() ? Number(maxUses) : null;
    if (uses != null && (!Number.isInteger(uses) || uses < 1)) errs.maxUses = "A whole number above 0, or empty for unlimited.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setServerError(null);
    create.mutate(
      { name: name.trim(), labels: parsed ?? {}, expires_in_days: Number(days), max_uses: uses },
      {
        onSuccess: (t) => {
          setCreated(t);
          toast.success("Enrolment token created.");
        },
        onError: (err) => setServerError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent className={created ? "max-w-2xl" : "max-w-lg"}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {created && <CheckCircle2Icon className="size-5 text-savings" />}
            {created ? "Install the agent" : "Add a host"}
          </DialogTitle>
          <DialogDescription>
            {created
              ? "Run one of these on each GPU machine. The same token can enrol many machines until it expires."
              : "Create an enrolment token, then start the agent on your GPU machines with it."}
          </DialogDescription>
        </DialogHeader>
        {created ? (
          <>
            <DialogBody>
              <Revealed created={created} />
            </DialogBody>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
            <DialogBody className="space-y-4">
              <Field label="Name" htmlFor="et-name" error={errors.name} labelExtra={<Hint term="enrolment" />}>
                <Input id="et-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="training nodes" />
              </Field>
              <Field label="Labels" htmlFor="et-labels" error={errors.labels} hint="Optional. Every host enrolled with this token gets them; rules and costs can use them.">
                <Input id="et-labels" value={labels} onChange={(e) => setLabels(e.target.value)} placeholder="env=prod,team=ml" />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Expires after" htmlFor="et-days">
                  <SimpleSelect id="et-days" value={days} onValueChange={(v) => setDays(v || "7")} options={EXPIRY} />
                </Field>
                <Field label="Max machines" htmlFor="et-uses" error={errors.maxUses} hint="Empty: unlimited">
                  <Input id="et-uses" inputMode="numeric" className="tabular" value={maxUses} onChange={(e) => setMaxUses(e.target.value)} />
                </Field>
              </div>
              {serverError && <FieldError>{serverError}</FieldError>}
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Creating..." : "Create token"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
