import { ShieldIcon } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { Surface } from "@/components/surface";
import { Button } from "@/components/ui/button";

/** Shown to viewers on pages the API serves only to admins and owners. */
export function AdminOnly({ what }: { what: string }) {
  return (
    <Surface>
      <EmptyState
        icon={ShieldIcon}
        title="Admins only"
        description={`${what} is visible to admins and owners. Ask an owner to change your role if you need it.`}
        action={
          <Button variant="secondary" size="sm" nativeButton={false} render={<Link href="/" />}>
            Back to overview
          </Button>
        }
      />
    </Surface>
  );
}
