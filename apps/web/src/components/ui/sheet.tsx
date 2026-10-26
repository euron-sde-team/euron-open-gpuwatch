"use client";

import * as React from "react";
import { Dialog as SheetPrimitive } from "@base-ui/react/dialog";
import { XIcon } from "lucide-react";

import { cn } from "@/lib/cn";

import { Button } from "./button";

function Sheet(props: SheetPrimitive.Root.Props) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />;
}

function SheetContent({
  className,
  children,
  side = "right",
  ...props
}: SheetPrimitive.Popup.Props & { side?: "right" | "left" }) {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Backdrop
        data-slot="sheet-overlay"
        className="fixed inset-0 z-50 bg-slate-950/35 transition-opacity duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0"
      />
      <SheetPrimitive.Popup
        data-slot="sheet-content"
        data-side={side}
        className={cn(
          "fixed inset-y-0 z-50 flex h-full w-full flex-col bg-popover text-sm text-popover-foreground shadow-[var(--elev-4)] transition duration-250 ease-[cubic-bezier(0.32,0.72,0,1)] outline-none sm:max-w-xl",
          "data-[side=right]:right-0 data-[side=right]:data-ending-style:translate-x-full data-[side=right]:data-starting-style:translate-x-full",
          "data-[side=left]:left-0 data-[side=left]:max-w-72 data-[side=left]:data-ending-style:-translate-x-full data-[side=left]:data-starting-style:-translate-x-full",
          className,
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close
          data-slot="sheet-close"
          render={<Button variant="subtle" size="icon-sm" className="absolute top-3.5 right-3.5" />}
        >
          <XIcon />
          <span className="sr-only">Close</span>
        </SheetPrimitive.Close>
      </SheetPrimitive.Popup>
    </SheetPrimitive.Portal>
  );
}

function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="sheet-header" className={cn("flex flex-col gap-1 px-5 pt-5 pb-4 pr-14", className)} {...props} />;
}

function SheetBody({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="sheet-body" className={cn("min-h-0 flex-1 overflow-y-auto px-5 pb-6", className)} {...props} />;
}

function SheetTitle({ className, ...props }: SheetPrimitive.Title.Props) {
  return <SheetPrimitive.Title data-slot="sheet-title" className={cn("text-base font-semibold tracking-[-0.01em]", className)} {...props} />;
}

function SheetDescription({ className, ...props }: SheetPrimitive.Description.Props) {
  return (
    <SheetPrimitive.Description data-slot="sheet-description" className={cn("text-[13px] text-muted-foreground", className)} {...props} />
  );
}

export { Sheet, SheetContent, SheetHeader, SheetBody, SheetTitle, SheetDescription };
