"use client";

import { useTheme } from "@/lib/theme";

/**
 * Chart colors derived from the same theme tokens as the rest of the UI.
 *
 * Recharts paints SVG through `fill`/`stroke` attributes, which Tailwind
 * classes cannot reach, so charts read their colors from here and follow the
 * active theme. New charts call `useChartTheme()` instead of hardcoding hex.
 */

export interface ChartPalette {
  /** Grid and axes: legible but quieter than the data. */
  grid: string;
  axis: string;
  /** Tooltip surface, matching the cards. */
  tooltipBg: string;
  tooltipBorder: string;
  tooltipFg: string;
  /** Series colors by importance; the first is always the brand. */
  series: [string, string, string, string, string];
}

const DARK: ChartPalette = {
  grid: "rgba(150, 140, 144, 0.16)",
  axis: "#968c90",
  tooltipBg: "#191416",
  tooltipBorder: "rgba(255, 255, 255, 0.12)",
  tooltipFg: "#f7f9fb",
  series: ["#5591ff", "#47e2ff", "#c084fc", "#fbbf24", "#34d399"],
};

const LIGHT: ChartPalette = {
  grid: "rgba(86, 78, 81, 0.14)",
  axis: "#6f666a",
  tooltipBg: "#ffffff",
  tooltipBorder: "rgba(25, 20, 22, 0.12)",
  tooltipFg: "#11171a",
  series: ["#0a54e0", "#04b3d4", "#7c3aed", "#b45309", "#047857"],
};

export function useChartTheme(): ChartPalette {
  const { theme } = useTheme();
  return theme === "light" ? LIGHT : DARK;
}

/** Tooltip style in Recharts' shape (`contentStyle` + `labelStyle`). */
export function tooltipStyles(palette: ChartPalette) {
  return {
    contentStyle: {
      background: palette.tooltipBg,
      border: `1px solid ${palette.tooltipBorder}`,
      borderRadius: 12,
      fontSize: 12,
      boxShadow: "0 18px 40px -24px rgba(0,0,0,0.6)",
    },
    labelStyle: { color: palette.tooltipFg, fontWeight: 600 },
    itemStyle: { color: palette.tooltipFg },
  };
}

/** Uniform axis style: no axis line, no ticks. */
export function axisProps(palette: ChartPalette) {
  return {
    stroke: palette.axis,
    fontSize: 11,
    tickLine: false,
    axisLine: false,
    tick: { fill: palette.axis, fontSize: 11 },
  } as const;
}
