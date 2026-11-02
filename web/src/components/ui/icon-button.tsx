"use client";

import * as React from "react";
import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";
import { primaryFill } from "./_shared";

/**
 * Cream editorial IconButton: one glyph in the same materials as the Button.
 *
 * The default is a quiet oat square with a 0.5rem corner; `circle` rounds it
 * fully. `primary` is the flat terracotta fill, kept for the one action a
 * screen offers. Ghost suits toolbars and rows. Hover only deepens the fill;
 * nothing lifts or scales.
 */
const iconButtonVariants = cva(
  [
    "relative inline-flex shrink-0 select-none items-center justify-center",
    "transition-[background-color,color,border-color] duration-fast ease-out",
    "outline-none focus-visible:ring-3 focus-visible:ring-ring",
    "disabled:pointer-events-none disabled:bg-secondary disabled:text-(--foreground-disabled)",
    "data-[disabled]:pointer-events-none data-[disabled]:bg-secondary data-[disabled]:text-(--foreground-disabled)",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "bg-secondary text-secondary-foreground hover:bg-muted",
        primary: primaryFill,
        secondary: "bg-secondary text-secondary-foreground hover:bg-muted",
        ghost:
          "bg-transparent text-(--foreground-secondary) hover:bg-secondary hover:text-foreground data-[disabled]:bg-transparent disabled:bg-transparent",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-(--destructive-text)",
        outline:
          "border border-(--line-strong) bg-transparent text-foreground hover:bg-secondary data-[disabled]:border-border",
      },
      size: {
        xs: "size-7 [&_svg]:size-3.5",
        sm: "size-8 [&_svg]:size-4",
        default: "size-9 [&_svg]:size-4",
        lg: "size-11 [&_svg]:size-5",
        xl: "size-12 [&_svg]:size-6",
      },
      corners: {
        square: "rounded-md",
        circle: "rounded-full",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
      corners: "square",
    },
  },
);

/** Props for the IconButton. Give it an `aria-label`, since the glyph carries no text. */
export interface IconButtonProps
  extends
    Omit<ButtonPrimitive.Props, "className">,
    VariantProps<typeof iconButtonVariants> {
  className?: string;
}

const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, variant, size, corners, ...props }, ref) => (
    <ButtonPrimitive
      ref={ref}
      data-slot="icon-button"
      className={cn(iconButtonVariants({ variant, size, corners, className }))}
      {...props}
    />
  ),
);
IconButton.displayName = "IconButton";

export { IconButton, iconButtonVariants };
