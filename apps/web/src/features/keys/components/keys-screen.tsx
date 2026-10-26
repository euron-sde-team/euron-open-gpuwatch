"use client";

import { PlusIcon } from "lucide-react";
import * as React from "react";

import { PageHeader } from "@/components/page-header";
import { Surface } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { usePermissions } from "@/features/auth/api";
import type { ApiKey } from "@/lib/api/types";

import { CreateKeyDialog } from "./create-key-dialog";
import { KeysTable } from "./keys-table";

export function KeysScreen() {
  const { canWrite } = usePermissions();
  const [open, setOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<ApiKey | null>(null);
  const create = () => {
    setEditing(null);
    setOpen(true);
  };
  const [showRevoked, setShowRevoked] = React.useState(false);
  return (
    <>
      <PageHeader
        title="API keys"
        description="Read-only keys for automation against the REST API. Stored as a peppered hash; the full key is shown once at creation."
        actions={
          canWrite && (
            <Button onClick={create}>
              <PlusIcon />
              New key
            </Button>
          )
        }
      />
      <Surface className="overflow-hidden">
        <div className="flex items-center justify-end gap-2 px-5 pt-3.5 pb-1 text-[12.5px] text-muted-foreground">
          <label htmlFor="show-revoked">Show revoked</label>
          <Switch id="show-revoked" checked={showRevoked} onCheckedChange={setShowRevoked} />
        </div>
        <KeysTable includeRevoked={showRevoked} canWrite={canWrite} onCreate={create}
          onEdit={(k) => {
            setEditing(k);
            setOpen(true);
          }}
        />
      </Surface>
      <CreateKeyDialog open={open} onOpenChange={setOpen} editing={editing} />
    </>
  );
}
