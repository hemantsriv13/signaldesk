"use client";

import * as React from "react";
import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";
import { focusRing, primaryFill } from "./_shared";

/**
 * Cream editorial Button on a Base UI button: a flat block with a 0.5rem
 * corner.
 *
 * Type is the clean sans at medium weight. The primary is flat terracotta
 * with white type; hover deepens it and nothing else moves. The secondary is
 * an oat block, the outline a cream block behind a warm hairline, and the
 * solid variant is the warm ink block. A disabled button drops to an oat
 * well with faint type, whether the element is a native button or a link
 * rendered through `render`.
 */
const buttonVariants = cva(
  [
    "inline-flex max-w-full shrink-0 select-none items-center justify-center gap-2 whitespace-nowrap",
    "rounded-md font-medium",
    "transition-[background-color,color,border-color] duration-fast ease-out",
    focusRing,
    "disabled:pointer-events-none disabled:border-transparent disabled:bg-muted disabled:text-(--foreground-disabled)",
    "data-[disabled]:pointer-events-none data-[disabled]:border-transparent data-[disabled]:bg-muted data-[disabled]:text-(--foreground-disabled)",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        default: primaryFill,
        primary: primaryFill,
        // Warm ink block, for a strong action that is not the terracotta one.
        solid: "bg-foreground text-background hover:bg-foreground/85",
        secondary: "bg-secondary text-secondary-foreground hover:bg-muted",
        outline:
          "border border-(--line-strong) bg-background text-foreground hover:bg-secondary",
        ghost: "bg-transparent text-(--foreground-secondary) hover:bg-secondary hover:text-foreground",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        link: "h-auto rounded-sm px-0 text-(--primary-text) underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        default: "h-9 px-4 text-[0.9375rem]",
        lg: "h-11 px-5 text-base",
        icon: "size-9 px-0",
        "icon-sm": "size-8 px-0",
        "icon-lg": "size-11 px-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

/** Props for the Base UI Button. `asChild` turns a single child element into the button. */
export interface ButtonProps
  extends
    Omit<ButtonPrimitive.Props, "className">,
    VariantProps<typeof buttonVariants> {
  className?: string;
  /**
   * Renders the single child element as the button, for callers written
   * against the Radix API (`<Button asChild><a href="…" /></Button>`).
   * Base UI composes through `render`, so the child becomes that element.
   */
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, children, ...props }, ref) => {
    const classes = cn(buttonVariants({ variant, size, className }));

    if (asChild && React.isValidElement(children)) {
      return (
        <ButtonPrimitive
          ref={ref}
          data-slot="button"
          className={classes}
          nativeButton={false}
          {...props}
          render={children}
        />
      );
    }

    return (
      <ButtonPrimitive
        ref={ref}
        data-slot="button"
        className={classes}
        {...props}
      >
        {children}
      </ButtonPrimitive>
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
