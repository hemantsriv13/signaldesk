"use client";

import * as React from "react";
import { Separator as SeparatorPrimitive } from "@base-ui/react/separator";

import { cn } from "@/lib/utils";

/**
 * Cream editorial Separator: a warm hairline on the paper, across or upright.
 * It is the same rule that sits under table rows and around cards.
 */
const Separator = React.forwardRef<
  HTMLDivElement,
  Omit<SeparatorPrimitive.Props, "className"> & {
    className?: string;
    /**
     * Accepted so callers written for the Radix wrapper still compile. It has
     * no effect: the Base UI separator always carries role="separator".
     */
    decorative?: boolean;
  }
>(
  (
    { className, orientation = "horizontal", decorative: _decorative, ...props },
    ref,
  ) => (
    <SeparatorPrimitive
      ref={ref}
      data-slot="separator"
      orientation={orientation}
      className={cn(
        "shrink-0 bg-border",
        "data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full",
        "data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px",
        className,
      )}
      {...props}
    />
  ),
);
Separator.displayName = "Separator";

export { Separator };
