"use client";

import * as React from "react";
import { Slider as SliderPrimitive } from "@base-ui/react/slider";

import { cn } from "@/lib/utils";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

/**
 * Cream editorial Slider: a thin oat track with a flat terracotta range. Each
 * thumb is a pale knob ringed in terracotta. Pass an array value for a range;
 * the slider renders one thumb per value.
 */
const Slider = React.forwardRef<
  HTMLDivElement,
  WithClassName<SliderPrimitive.Root.Props>
>(({ className, defaultValue, value, min = 0, max = 100, ...props }, ref) => {
  const _values = Array.isArray(value)
    ? value
    : Array.isArray(defaultValue)
      ? defaultValue
      : [min];

  return (
    <SliderPrimitive.Root
      data-slot="slider"
      ref={ref}
      thumbAlignment="edge"
      defaultValue={defaultValue}
      value={value}
      min={min}
      max={max}
      className={cn(
        "relative w-full data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Control className="relative flex h-5 w-full touch-none select-none items-center">
        <SliderPrimitive.Track
          data-slot="slider-track"
          className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-muted"
        >
          <SliderPrimitive.Indicator
            data-slot="slider-range"
            className="rounded-full bg-primary"
          />
        </SliderPrimitive.Track>
        {Array.from({ length: _values.length }, (_, index) => (
          <SliderPrimitive.Thumb
            data-slot="slider-thumb"
            key={index}
            className={cn(
              "block size-4 shrink-0 cursor-grab rounded-full border-2 border-primary bg-(--thumb) shadow-(--shadow-thumb)",
              "transition-[box-shadow] duration-fast ease-out active:cursor-grabbing",
              "has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring",
              "data-[disabled]:pointer-events-none data-[disabled]:border-(--line-strong)",
            )}
          />
        ))}
      </SliderPrimitive.Control>
    </SliderPrimitive.Root>
  );
});
Slider.displayName = "Slider";

export { Slider };
