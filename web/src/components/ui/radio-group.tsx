"use client";

import { RadioGroup as RadioGroupPrimitive } from "@base-ui/react/radio-group";
import { Radio as RadioPrimitive } from "@base-ui/react/radio";

import { cn } from "@/lib/utils";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

/** Cream editorial RadioGroup: a column of choices with 0.75rem between them. */
function RadioGroup({
  className,
  ...props
}: WithClassName<RadioGroupPrimitive.Props>) {
  return (
    <RadioGroupPrimitive
      data-slot="radio-group"
      className={cn("grid gap-3", className)}
      {...props}
    />
  );
}
RadioGroup.displayName = "RadioGroup";

/**
 * Cream editorial RadioGroupItem: a 1rem circle of pale paper with a warm
 * edge. Chosen, the edge turns terracotta and a terracotta dot sits at the
 * centre, the same flat colour as the primary button.
 */
function RadioGroupItem({
  className,
  ...props
}: WithClassName<RadioPrimitive.Root.Props>) {
  return (
    <RadioPrimitive.Root
      data-slot="radio-group-item"
      className={cn(
        "flex aspect-square size-4 shrink-0 items-center justify-center rounded-full border border-(--control) bg-(--field)",
        "transition-[border-color,box-shadow] duration-fast ease-out",
        "outline-none focus-visible:ring-3 focus-visible:ring-ring",
        "data-[checked]:border-primary",
        "data-[disabled]:cursor-not-allowed data-[disabled]:border-(--line-strong) data-[disabled]:bg-secondary",
        className,
      )}
      {...props}
    >
      <RadioPrimitive.Indicator
        data-slot="radio-group-indicator"
        className="flex size-full items-center justify-center"
      >
        <span className="block size-2 rounded-full bg-primary in-data-[disabled]:bg-(--foreground-disabled)" />
      </RadioPrimitive.Indicator>
    </RadioPrimitive.Root>
  );
}
RadioGroupItem.displayName = "RadioGroupItem";

export { RadioGroup, RadioGroupItem };
