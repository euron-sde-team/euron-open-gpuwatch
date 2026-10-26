import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/cn";

const buttonVariants = cva(
  [
    "group/button relative inline-flex shrink-0 items-center justify-center gap-2",
    "border border-transparent font-medium whitespace-nowrap select-none",
    "transition-[background-color,color,box-shadow,transform,opacity] duration-150 outline-none",
    "focus-visible:ring-[3px] focus-visible:ring-ring/40",
    "active:scale-[0.98]",
    "disabled:pointer-events-none disabled:opacity-45 data-disabled:pointer-events-none data-disabled:opacity-45",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-[var(--elev-1)] hover:brightness-110",
        secondary: "bg-muted text-foreground hover:bg-accent",
        outline: "bg-card text-foreground shadow-[var(--elev-1)] ring-1 ring-border hover:bg-muted ring-inset",
        ghost: "text-foreground hover:bg-muted aria-expanded:bg-muted",
        subtle: "text-muted-foreground hover:bg-muted hover:text-foreground aria-expanded:bg-muted",
        destructive: "bg-danger text-danger-foreground shadow-[var(--elev-1)] hover:brightness-110",
        "destructive-soft": "bg-danger-soft text-danger hover:brightness-95 dark:hover:brightness-125",
        link: "h-auto px-0 text-primary underline-offset-4 hover:underline active:scale-100",
      },
      size: {
        default: "h-9 rounded-lg px-3.5 text-sm",
        xs: "h-7 gap-1.5 rounded-md px-2.5 text-xs [&_svg:not([class*='size-'])]:size-3.5",
        sm: "h-8 gap-1.5 rounded-md px-3 text-[13px]",
        lg: "h-10 rounded-lg px-5 text-sm",
        icon: "size-9 rounded-lg",
        "icon-sm": "size-8 rounded-md",
        "icon-xs": "size-7 rounded-md [&_svg:not([class*='size-'])]:size-3.5",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return <ButtonPrimitive data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

export { Button, buttonVariants };
