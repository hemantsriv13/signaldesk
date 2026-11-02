"use client";

import * as React from "react";

// Base UI has no AspectRatio primitive, so this is a plain div with the CSS
// aspect-ratio property. position: relative and width: 100% keep absolutely
// positioned children (a filled image, for example) inside the frame.

/** Props for AspectRatio. `ratio` is width over height, such as 16 / 9. */
export interface AspectRatioProps
  extends React.ComponentPropsWithoutRef<"div"> {
  ratio?: number;
}

/** Cream editorial AspectRatio: a frame that holds its shape as its width changes. */
const AspectRatio = React.forwardRef<HTMLDivElement, AspectRatioProps>(
  ({ ratio = 1, style, ...props }, ref) => (
    <div
      ref={ref}
      data-slot="aspect-ratio"
      style={{
        position: "relative",
        width: "100%",
        aspectRatio: String(ratio),
        ...style,
      }}
      {...props}
    />
  ),
);
AspectRatio.displayName = "AspectRatio";

export { AspectRatio };
