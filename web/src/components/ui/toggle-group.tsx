"use client";

import * as React from "react";
import { Toggle as TogglePrimitive } from "@base-ui/react/toggle";
import { ToggleGroup as ToggleGroupPrimitive } from "@base-ui/react/toggle-group";
import { type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";
import { toggleVariants } from "./toggle";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

const ToggleGroupContext = React.createContext<
  VariantProps<typeof toggleVariants>
>({});

/**
 * Cream editorial ToggleGroup: a row of category tabs with a small gap, so
 * each choice stays its own tab. A pressed item takes the oat block; the
 * group passes its variant and size down to every item.
 */
function ToggleGroup({
  className,
  variant,
  size,
  children,
  ...props
}: WithClassName<ToggleGroupPrimitive.Props<string>> &
  VariantProps<typeof toggleVariants>) {
  return (
    <ToggleGroupPrimitive
      data-slot="toggle-group"
      className={cn(
        "inline-flex flex-wrap items-center gap-1",
        "data-[orientation=vertical]:flex-col data-[orientation=vertical]:items-stretch",
        className,
      )}
      {...props}
    >
      <ToggleGroupContext.Provider value={{ variant, size }}>
        {children}
      </ToggleGroupContext.Provider>
    </ToggleGroupPrimitive>
  );
}
ToggleGroup.displayName = "ToggleGroup";

/** One tab inside a ToggleGroup. It takes the group's variant and size unless the group leaves them unset. */
function ToggleGroupItem({
  className,
  variant,
  size,
  ...props
}: WithClassName<TogglePrimitive.Props<string>> &
  VariantProps<typeof toggleVariants>) {
  const context = React.useContext(ToggleGroupContext);

  return (
    <TogglePrimitive
      data-slot="toggle-group-item"
      className={cn(
        toggleVariants({
          variant: context.variant ?? variant,
          size: context.size ?? size,
        }),
        className,
      )}
      {...props}
    />
  );
}
ToggleGroupItem.displayName = "ToggleGroupItem";

export { ToggleGroup, ToggleGroupItem };
