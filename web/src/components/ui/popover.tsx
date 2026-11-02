"use client";

import * as React from "react";
import { Popover as PopoverPrimitive } from "@base-ui/react/popover";

import { cn } from "@/lib/utils";
import { popoverSurface, popoverMotion } from "./_shared";

// Base UI accepts a state function for className; these wrappers merge it with
// cn(), so they take a plain string.
type WithClassName<P> = Omit<P, "className"> & { className?: string };

/** Cream editorial Popover root: owns the open state of one floating panel. */
const Popover = PopoverPrimitive.Root;

/** The control the popover opens from. */
const PopoverTrigger = PopoverPrimitive.Trigger;

/**
 * Cream editorial popover panel: the lightest paper, 18rem wide, edged by a
 * warm hairline inside its soft shadow. It stacks content with a 0.75rem gap
 * and settles from its anchor as it fades in.
 */
const PopoverContent = React.forwardRef<
  HTMLDivElement,
  WithClassName<PopoverPrimitive.Popup.Props> &
    Pick<
      PopoverPrimitive.Positioner.Props,
      "align" | "alignOffset" | "side" | "sideOffset"
    >
>(
  (
    {
      className,
      align = "center",
      alignOffset,
      side,
      sideOffset = 6,
      ...props
    },
    ref,
  ) => (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Positioner
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
        className="isolate z-50 outline-none"
      >
        <PopoverPrimitive.Popup
          ref={ref}
          data-slot="popover-content"
          className={cn(
            popoverSurface,
            popoverMotion,
            "flex w-72 max-w-(--available-width) flex-col gap-3 p-4 text-sm",
            className,
          )}
          {...props}
        />
      </PopoverPrimitive.Positioner>
    </PopoverPrimitive.Portal>
  ),
);
PopoverContent.displayName = "PopoverContent";

export { Popover, PopoverTrigger, PopoverContent };
