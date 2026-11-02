export const CHART_SCALE_VARS = [
  "var(--chart-scale-01, color-mix(in oklch, var(--chart-1) 12%, var(--background)))",
  "var(--chart-scale-02, color-mix(in oklch, var(--chart-1) 32%, var(--background)))",
  "var(--chart-scale-03, color-mix(in oklch, var(--chart-1) 55%, var(--background)))",
  "var(--chart-scale-04, color-mix(in oklch, var(--chart-1) 78%, var(--background)))",
  "var(--chart-scale-05, var(--chart-1))",
] as const;

export type ChartScaleVars = typeof CHART_SCALE_VARS;

export const chartScaleCssVars = {
  scale01: CHART_SCALE_VARS[0],
  scale02: CHART_SCALE_VARS[1],
  scale03: CHART_SCALE_VARS[2],
  scale04: CHART_SCALE_VARS[3],
  scale05: CHART_SCALE_VARS[4],
  patternColor: "var(--chart-scale-pattern-color, var(--background))",
} as const;
