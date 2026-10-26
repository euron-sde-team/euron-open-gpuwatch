import { CompassIcon } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-background p-6">
      <div className="surface max-w-md px-8 py-10 text-center">
        <div className="mx-auto mb-4 flex size-11 items-center justify-center rounded-xl bg-primary-soft text-primary">
          <CompassIcon className="size-5" />
        </div>
        <h1 className="text-lg font-semibold">Page not found</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          This address does not match any GPUWatch page. It may have moved, or the link is mistyped.
        </p>
        <Link href="/" className={buttonVariants({ className: "mt-5" })}>
          Back to the overview
        </Link>
      </div>
    </div>
  );
}
