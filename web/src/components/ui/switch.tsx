"use client";

import { Switch as SwitchPrimitive } from "@base-ui/react/switch";

import { cn } from "@/lib/utils";
import { controlChecked } from "./_shared";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

/**
 * Cream editorial Switch: a 2.25rem by 1.25rem track in the strong warm line
 * colour with a pale knob. On, the track turns flat terracotta, the same fill
 * as the primary button, and the knob slides across.
 */
function Switch({ className, ...props }: WithClassName<SwitchPrimitive.Root.Props>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border border-transparent bg-(--line-strong) p-0.5",
        "transition-colors duration-fast ease-out",
        "hover:data-[unchecked]:bg-(--control)",
        "outline-none focus-visible:ring-3 focus-visible:ring-ring",
        "data-[disabled]:cursor-not-allowed data-[disabled]:bg-muted",
        controlChecked,
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className={cn(
          "pointer-events-none block size-4 rounded-full bg-(--thumb) shadow-(--shadow-thumb)",
          "transition-transform duration-fast ease-out motion-reduce:transition-none",
          "data-[checked]:translate-x-3.5 data-[unchecked]:translate-x-0",
          "data-[disabled]:shadow-none",
        )}
      />
    </SwitchPrimitive.Root>
  );
}
Switch.displayName = "Switch";

export { Switch };
