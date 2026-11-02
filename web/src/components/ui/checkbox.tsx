"use client";

import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox";

import { cn } from "@/lib/utils";
import { controlChecked } from "./_shared";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

/**
 * Cream editorial Checkbox: a 1rem paper box with a small corner and a warm
 * grey edge. Checked or mixed, it fills with the flat terracotta of the
 * primary button and shows a white tick or dash. Base UI owns the checked
 * state, so a controlled parent passes `checked` straight through.
 */
function Checkbox({
  className,
  indeterminate,
  ...props
}: WithClassName<CheckboxPrimitive.Root.Props>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      indeterminate={indeterminate}
      className={cn(
        "peer inline-flex size-4 shrink-0 items-center justify-center rounded-sm border border-(--control) bg-(--field) text-primary-foreground",
        "transition-[background-color,border-color] duration-fast ease-out",
        "outline-none focus-visible:ring-3 focus-visible:ring-ring",
        "data-[disabled]:cursor-not-allowed data-[disabled]:border-(--line-strong) data-[disabled]:bg-secondary",
        controlChecked,
        "data-[indeterminate]:border-primary data-[indeterminate]:bg-primary",
        "data-[disabled]:data-[indeterminate]:border-(--line-strong) data-[disabled]:data-[indeterminate]:bg-muted data-[disabled]:data-[indeterminate]:text-(--foreground-disabled)",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="flex size-full items-center justify-center text-current"
      >
        {indeterminate ? (
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="size-3">
            <path d="M3.5 8h9" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" />
          </svg>
        ) : (
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="size-3">
            <path
              d="M3 8.5 6.25 11.5 13 4.5"
              stroke="currentColor"
              strokeWidth="2.25"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
Checkbox.displayName = "Checkbox";

export { Checkbox };
