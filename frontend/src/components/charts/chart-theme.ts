/** Chart color system — validated for dark surface #10151f (CVD-safe, fixed order).
 * Categorical hues are assigned in this fixed order and never cycled. */
export const CHART_SERIES = ["#0284c7", "#059669", "#d97706", "#7c3aed"] as const;

export const CHART_GRID = "#1c2433";
export const CHART_AXIS = "#8b98ad";
export const CHART_TOOLTIP_BG = "#10151f";

export const tooltipStyle = {
  backgroundColor: CHART_TOOLTIP_BG,
  border: `1px solid ${CHART_GRID}`,
  borderRadius: 8,
  fontSize: 12,
  color: "#dbe2ef",
} as const;
