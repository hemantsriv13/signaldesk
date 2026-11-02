"use client";

import * as React from "react";
import { Avatar as AvatarPrimitive } from "@base-ui/react/avatar";

import { cn } from "@/lib/utils";

type WithClassName<P> = Omit<P, "className"> & { className?: string };

/**
 * Cream editorial Avatar: a 2.5rem round photo, or initials in secondary
 * ink on an oat disc when there is no photo. Resize it with a size class
 * (size-6, size-8, size-14); the initials follow the circle.
 */
const Avatar = React.forwardRef<
  HTMLSpanElement,
  WithClassName<AvatarPrimitive.Root.Props>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Root
    ref={ref}
    data-slot="avatar"
    className={cn(
      "@container relative flex size-10 shrink-0 select-none overflow-hidden rounded-full",
      className,
    )}
    {...props}
  />
));
Avatar.displayName = "Avatar";

/** The photo, cropped to fill the circle. */
const AvatarImage = React.forwardRef<
  HTMLImageElement,
  WithClassName<AvatarPrimitive.Image.Props>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Image
    ref={ref}
    data-slot="avatar-image"
    className={cn("aspect-square size-full object-cover", className)}
    {...props}
  />
));
AvatarImage.displayName = "AvatarImage";

/** Initials on an oat disc, shown while the photo loads or when it fails. */
const AvatarFallback = React.forwardRef<
  HTMLSpanElement,
  WithClassName<AvatarPrimitive.Fallback.Props>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Fallback
    ref={ref}
    data-slot="avatar-fallback"
    className={cn(
      "flex size-full items-center justify-center rounded-full bg-muted",
      "text-sm font-medium text-(--foreground-secondary)",
      "@max-[2.25rem]:text-xs @min-[3rem]:text-lg",
      className,
    )}
    {...props}
  />
));
AvatarFallback.displayName = "AvatarFallback";

export { Avatar, AvatarImage, AvatarFallback };
