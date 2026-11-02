"use client";

import * as React from "react";
import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip";

import { cn } from "@/lib/utils";
import { popupMotion } from "./_shared";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

/** Shares the open and close delay across every tooltip inside it. */
const TooltipProvider = TooltipPrimitive.Provider;

/** Cream editorial Tooltip root: a short label for one control. */
const Tooltip = TooltipPrimitive.Root;

/** The control the tooltip describes. */
const TooltipTrigger = TooltipPrimitive.Trigger;

/**
 * Cream editorial tooltip: a small chip of warm ink with cream type, a
 * 0.5rem corner and no arrow. It grows from the control and fades in.
 */
const TooltipContent = React.forwardRef<
  HTMLDivElement,
  WithClassName<TooltipPrimitive.Popup.Props> &
    Pick<
      TooltipPrimitive.Positioner.Props,
      "align" | "alignOffset" | "side" | "sideOffset"
    >
>(({ className, align, alignOffset, side, sideOffset = 6, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Positioner
      align={align}
      alignOffset={alignOffset}
      side={side}
      sideOffset={sideOffset}
      className="isolate z-50"
    >
      <TooltipPrimitive.Popup
        ref={ref}
        data-slot="tooltip-content"
        className={cn(
          popupMotion,
          "max-w-64 rounded-md bg-foreground px-2 py-1 text-xs leading-snug text-background",
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Positioner>
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = "TooltipContent";

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
