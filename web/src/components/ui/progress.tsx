"use client";

import * as React from "react";
import { Progress as ProgressPrimitive } from "@base-ui/react/progress";

import { cn } from "@/lib/utils";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

/**
 * Cream editorial Progress: a thin oat track with a flat terracotta fill.
 * Leave `value` unset for an unknown amount, and a short fill pulses instead.
 */
const Progress = React.forwardRef<
  HTMLDivElement,
  Omit<WithClassName<ProgressPrimitive.Root.Props>, "value"> & {
    value?: ProgressPrimitive.Root.Props["value"];
  }
>(({ className, value, ...props }, ref) => (
  <ProgressPrimitive.Root
    ref={ref}
    data-slot="progress"
    value={value ?? null}
    className={cn(
      "relative h-1.5 w-full overflow-hidden rounded-full bg-muted",
      className,
    )}
    {...props}
  >
    <ProgressPrimitive.Track data-slot="progress-track" className="size-full">
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className="h-full rounded-full bg-primary transition-[width] duration-fast ease-out data-[indeterminate]:w-1/3 data-[indeterminate]:animate-pulse motion-reduce:transition-none"
      />
    </ProgressPrimitive.Track>
  </ProgressPrimitive.Root>
));
Progress.displayName = "Progress";

export { Progress };
