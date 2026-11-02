"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Cream editorial Label: warm ink in the sans at the body size, medium
 * weight, so it names a field without competing with it. When its control
 * is disabled the label fades to the disabled ink.
 *
 * Base UI has no label primitive, so this is a native label. Base UI
 * controls mark a disabled state with data-disabled rather than the
 * disabled attribute, so the label watches both.
 */
const Label = React.forwardRef<
  HTMLLabelElement,
  React.ComponentPropsWithoutRef<"label">
>(({ className, ...props }, ref) => (
  <label
    ref={ref}
    data-slot="label"
    className={cn(
      "flex select-none items-center gap-2 text-sm font-medium leading-snug text-foreground",
      "peer-disabled:cursor-not-allowed peer-disabled:text-(--foreground-disabled)",
      "peer-data-[disabled]:cursor-not-allowed peer-data-[disabled]:text-(--foreground-disabled)",
      className,
    )}
    {...props}
  />
));
Label.displayName = "Label";

export { Label };
