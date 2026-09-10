export const chartColors = {
  grid: "#23272f",
  axis: "#656d78",
  good: "#3ecf8e",
  warn: "#e0a63e",
  bad: "#e2555a",
  network: "#4fb3d9",
  synthetic: "#9d7de8",
  idle: "#5a6270",
  text: "#9aa1ac",
};

export const tooltipStyle = {
  contentStyle: {
    background: "#15181d",
    border: "1px solid #2c313b",
    borderRadius: 6,
    fontSize: 11,
    fontFamily: "var(--font-geist-mono)",
    color: "#e7e9ec",
  },
  labelStyle: { color: "#9aa1ac", marginBottom: 4 },
  itemStyle: { padding: 0 },
};

export const CLASS_COLOR_SEQUENCE = [
  chartColors.network,
  chartColors.synthetic,
  chartColors.warn,
  chartColors.bad,
  chartColors.good,
  "#e08fc0",
  "#7ec9e0",
];
