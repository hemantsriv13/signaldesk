"use client";

import * as React from "react";
import { Toggle as TogglePrimitive } from "@base-ui/react/toggle";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";
import { pressedWash } from "./_shared";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

/**
 * Cream editorial Toggle: a button that holds its state. Off, it is a quiet
 * label that takes an oat wash on hover, or a hairline chip on the paper.
 * Pressed, it becomes the oat category tab with ink type. Terracotta stays
 * with the one primary action.
 */
const toggleVariants = cva(
  [
    "inline-flex shrink-0 select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-transparent",
    "font-medium text-(--foreground-secondary)",
    "transition-[background-color,border-color,color] duration-fast ease-out",
    "outline-none focus-visible:ring-3 focus-visible:ring-ring",
    "data-[disabled]:pointer-events-none data-[disabled]:cursor-not-allowed data-[disabled]:text-(--foreground-disabled)",
    pressedWash,
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        default:
          "bg-transparent hover:not-data-[pressed]:bg-secondary hover:not-data-[pressed]:text-foreground",
        outline:
          "border-(--line-strong) bg-background hover:not-data-[pressed]:bg-secondary hover:not-data-[pressed]:text-foreground data-[disabled]:border-border",
      },
      size: {
        sm: "h-8 px-2.5 text-xs",
        default: "h-9 px-3 text-sm",
        lg: "h-10 px-4 text-sm",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

const Toggle = React.forwardRef<
  HTMLButtonElement,
  WithClassName<TogglePrimitive.Props> & VariantProps<typeof toggleVariants>
>(({ className, variant, size, ...props }, ref) => (
  <TogglePrimitive
    ref={ref}
    data-slot="toggle"
    className={cn(toggleVariants({ variant, size, className }))}
    {...props}
  />
));
Toggle.displayName = "Toggle";

export { Toggle, toggleVariants };
