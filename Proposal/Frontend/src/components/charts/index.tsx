/**
 * Chart primitives for the Title XI Deal Management Portal.
 *
 * Built on Recharts (per spec §7.1). All primitives expose the same API
 * the role dashboards already consume, so this module is a pure
 * implementation swap from the previous hand-rolled SVG version.
 *
 * Components exported:
 *   - DonutChart           — distribution as a ring + center label
 *   - HorizontalBars       — labeled horizontal bar chart
 *   - StackedHBar          — single horizontal bar split by category
 *   - VerticalBars         — column chart with optional comparison series
 *   - LineChart            — single-series line + filled area trend
 *   - MultiLineChart       — multi-series line trend
 *   - Sparkline            — tiny inline trend line
 *   - GaugeArc             — half-circle gauge for percent / progress
 *   - FunnelChart          — staged funnel (e.g. lifecycle conversion)
 *   - HeatmapMatrix        — grid heatmap for calendar / matrix data
 *   - ProgressMeter        — labeled progress bar
 *   - LegendDot            — small color swatch for legend rows
 */

import * as React from 'react';
import {
  Area,
  AreaChart as RAreaChart,
  Bar,
  BarChart as RBarChart,
  CartesianGrid,
  Cell,
  Funnel,
  FunnelChart as RFunnelChart,
  LabelList,
  Legend,
  Line,
  LineChart as RLineChart,
  PieChart as RPieChart,
  Pie,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { cn } from '@/lib/utils';

// ──────────────────────────────────────────────────────────────────────────
// Color palette — Tailwind theme colors as raw hex so they work inside SVG
// ──────────────────────────────────────────────────────────────────────────
export const CHART_PALETTE = {
  federalBlue: '#1F5AA8',
  federalBlueDark: '#143B71',
  federalBlueLight: '#9BBAE3',
  dotNavy: '#0F2A4A',
  successGreen: '#15803D',
  successGreenLight: '#86EFAC',
  alertAmber: '#B45309',
  alertAmberLight: '#FCD34D',
  alertRed: '#B91C1C',
  alertRedLight: '#FCA5A5',
  neutral: '#4B5563',
  neutralLight: '#CBD5E1',
  neutralMuted: '#94A3B8',
  border: '#E2E8F0',
  card: '#FFFFFF',
} as const;

/** Default categorical color rotation. */
export const SERIES_COLORS = [
  CHART_PALETTE.federalBlue,
  CHART_PALETTE.successGreen,
  CHART_PALETTE.alertAmber,
  CHART_PALETTE.alertRed,
  CHART_PALETTE.dotNavy,
  CHART_PALETTE.neutral,
  '#7C3AED', // violet
  '#0891B2', // cyan
  '#EA580C', // orange
  '#65A30D', // lime
];

const TOOLTIP_STYLE = {
  background: '#FFFFFF',
  border: '1px solid #E2E8F0',
  borderRadius: 6,
  fontSize: 12,
  padding: '6px 10px',
  boxShadow: '0 4px 12px -2px rgb(15 42 74 / 0.08), 0 2px 4px -2px rgb(15 42 74 / 0.06)',
  // Recharts inlines its content style; keep this fully opaque so center
  // labels / underlying chart elements never bleed through tooltip text.
};

/**
 * Wrapper style applied via the Recharts `wrapperStyle` prop so the tooltip's
 * outer floating div renders ABOVE absolutely-positioned overlays (the donut's
 * center label, status badges, etc.). Without this, the tooltip can land
 * under the overlay and produce overlapping text.
 */
const TOOLTIP_WRAPPER_STYLE: React.CSSProperties = {
  zIndex: 50,
  outline: 'none',
};

const fmtCount = (n: number) => new Intl.NumberFormat('en-US').format(n);

/** Coerce Recharts' loose value type to a number for our formatters. */
function toNum(v: unknown): number {
  if (typeof v === 'number') return v;
  if (typeof v === 'string') {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  }
  if (Array.isArray(v) && v.length > 0) return toNum(v[0]);
  return 0;
}

// ──────────────────────────────────────────────────────────────────────────
// LegendDot
// ──────────────────────────────────────────────────────────────────────────
export function LegendDot({
  color,
  label,
  value,
  className,
}: {
  color: string;
  label: React.ReactNode;
  value?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex items-center justify-between gap-2 text-xs leading-tight',
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
          style={{ backgroundColor: color }}
        />
        <span className="truncate text-muted-foreground">{label}</span>
      </div>
      {value != null ? (
        <span className="tabular-nums font-medium text-foreground">{value}</span>
      ) : null}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// DonutChart  — Recharts <Pie>
// ──────────────────────────────────────────────────────────────────────────
export interface DonutDatum {
  key: string;
  label: string;
  value: number;
  color?: string;
}

export function DonutChart({
  data,
  size = 180,
  thickness = 28,
  centerLabel,
  centerValue,
  showLegend = true,
  layout = 'stacked',
  className,
}: {
  data: DonutDatum[];
  size?: number;
  thickness?: number;
  centerLabel?: React.ReactNode;
  centerValue?: React.ReactNode;
  showLegend?: boolean;
  /**
   * `'stacked'` (default): donut centered with legend in a 2-column grid
   * below — readable across narrow cards, long labels, and many rows.
   * `'side'`: donut on the left, legend in a vertical column on the right
   * — only useful for short legends where horizontal compactness wins.
   */
  layout?: 'side' | 'stacked';
  className?: string;
}) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const outerRadius = size / 2 - 1;
  const innerRadius = Math.max(8, outerRadius - thickness);
  const stacked = layout === 'stacked';

  // Track which slice is hovered so we can render a custom tooltip pill
  // BELOW the donut — keeps the tooltip out of the ring entirely so it never
  // overlaps the center label.
  const [hoveredIndex, setHoveredIndex] = React.useState<number | null>(null);
  const hovered = hoveredIndex != null ? data[hoveredIndex] : null;
  const hoveredColor = hovered
    ? hovered.color ?? SERIES_COLORS[(hoveredIndex ?? 0) % SERIES_COLORS.length]
    : null;
  const hoveredPct = hovered && total > 0 ? (hovered.value / total) * 100 : 0;

  return (
    // Outer container is the positioning context for the hover pill.
    // - Side layout: pill is absolutely positioned at the container's
    //   bottom-left so its width can grow inside the card without ever
    //   shifting the donut or legend; `pb-8` reserves the visual slot.
    // - Stacked layout: pill sits in flex flow between donut and legend
    //   with its h-6 always reserved (opacity-0 when idle), so layout
    //   never shifts on hover, and items-center keeps it centered.
    <div
      className={cn(
        'relative flex',
        stacked ? 'flex-col items-center gap-2' : 'items-center gap-5 pb-8',
        className,
      )}
    >
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <ResponsiveContainer width="100%" height="100%">
          <RPieChart>
            {/* Recharts' built-in tooltip is intentionally omitted here; we
                render a custom pill below the donut instead so the tooltip
                text never overlaps the center label. */}
            <Pie
              data={data}
              dataKey="value"
              nameKey="label"
              cx="50%"
              cy="50%"
              innerRadius={innerRadius}
              outerRadius={outerRadius}
              startAngle={90}
              endAngle={-270}
              paddingAngle={data.length > 1 ? 1 : 0}
              isAnimationActive={false}
              stroke={CHART_PALETTE.card}
              strokeWidth={1.5}
              onMouseEnter={(_, idx) => setHoveredIndex(idx)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              {data.map((d, i) => (
                <Cell
                  key={d.key}
                  fill={d.color ?? SERIES_COLORS[i % SERIES_COLORS.length]}
                />
              ))}
            </Pie>
          </RPieChart>
        </ResponsiveContainer>
        {/* Center label overlay — always visible, no longer competing with
            the tooltip. */}
        {total > 0 ? (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-lg font-semibold leading-none text-foreground">
              {centerValue ?? fmtCount(total)}
            </span>
            <span className="mt-1 text-2xs text-muted-foreground tracking-[0.06em]">
              {centerLabel ?? 'TOTAL'}
            </span>
          </div>
        ) : (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
            No data
          </div>
        )}
      </div>

      {/* Hover pill — placement depends on layout (see outer container
          comment). In stacked layout it sits as a centered flex item
          between donut and legend; in side layout it stays absolutely
          positioned at the outer bottom-left. Either way h-6 is always
          reserved and opacity transitions on hover so layout never shifts. */}
      <div
        aria-live="polite"
        className={cn(
          'pointer-events-none flex h-6 max-w-full items-center gap-1.5 overflow-hidden rounded-full border bg-card px-3 shadow-xs transition-opacity',
          stacked ? '' : 'absolute bottom-0 left-0 z-10',
          hovered ? 'opacity-100' : 'opacity-0',
        )}
        style={{ borderColor: hoveredColor ?? CHART_PALETTE.border }}
      >
        {hovered ? (
          <>
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-sm"
              style={{ backgroundColor: hoveredColor ?? undefined }}
              aria-hidden
            />
            <span className="min-w-0 truncate text-xs font-medium text-foreground">
              {hovered.label}
            </span>
            <span className="shrink-0 text-2xs tabular-nums text-muted-foreground">
              {fmtCount(hovered.value)} ({hoveredPct.toFixed(0)}%)
            </span>
          </>
        ) : null}
      </div>

      {showLegend ? (
        stacked ? (
          <ul className="grid w-full grid-cols-1 gap-x-4 gap-y-1.5 border-t border-border/60 pt-3 sm:grid-cols-2">
            {data.map((d, i) => {
              const pct = total > 0 ? (d.value / total) * 100 : 0;
              const color = d.color ?? SERIES_COLORS[i % SERIES_COLORS.length];
              return (
                <li
                  key={d.key}
                  className="flex items-center justify-between gap-3 text-xs"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                      style={{ background: color }}
                      aria-hidden
                    />
                    <span className="truncate text-muted-foreground">
                      {d.label}
                    </span>
                  </div>
                  <span className="shrink-0 whitespace-nowrap tabular-nums font-medium text-foreground">
                    {fmtCount(d.value)}{' '}
                    <span className="font-normal text-muted-foreground">
                      ({pct.toFixed(0)}%)
                    </span>
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            {data.map((d, i) => {
              const pct = total > 0 ? (d.value / total) * 100 : 0;
              return (
                <LegendDot
                  key={d.key}
                  color={d.color ?? SERIES_COLORS[i % SERIES_COLORS.length]}
                  label={d.label}
                  value={
                    <span>
                      {fmtCount(d.value)}{' '}
                      <span className="text-muted-foreground">({pct.toFixed(0)}%)</span>
                    </span>
                  }
                />
              );
            })}
          </div>
        )
      ) : null}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// HorizontalBars — Recharts BarChart layout="vertical"
// ──────────────────────────────────────────────────────────────────────────
export interface HBarDatum {
  key: string;
  label: React.ReactNode;
  value: number;
  color?: string;
  hint?: React.ReactNode;
}

export function HorizontalBars({
  data,
  max,
  showValueLabels = true,
  className,
  emptyMessage = 'No data to display.',
  height,
  labelWidth = 'w-44',
  unit,
  barSize = 14,
  fill = false,
}: {
  data: HBarDatum[];
  max?: number;
  showValueLabels?: boolean;
  className?: string;
  emptyMessage?: string;
  /** Per-row height in px (label band + spacing). Total chart height = rows * height + padding. */
  height?: number;
  /** Tailwind class for label column width. (Approximation in px is derived below.) */
  labelWidth?: string;
  /** Append a unit to ticks + value labels (e.g. '%'). Counts are shown as whole numbers. */
  unit?: string;
  /** Bar thickness in px. */
  barSize?: number;
  /**
   * Grow to fill the parent's height (for a stretched flex card) instead of a
   * fixed pixel height, so paired cards line up without a bottom gap or a
   * centering offset. The computed height stays as a minHeight floor, so the
   * chart always has a non-zero measured height and can never render blank.
   * Parent must be a flex column with a definite height.
   */
  fill?: boolean;
}) {
  if (data.length === 0) {
    return <div className={cn('text-sm text-muted-foreground', className)}>{emptyMessage}</div>;
  }
  // Airier row band so few-category charts don't look chunky and the chart
  // fills more of its card (less dead space next to taller widgets).
  const rowH = height ?? 38;
  // Height tracks the row count with a small floor + axis padding, so charts
  // with only one or two bars stay compact instead of leaving a tall empty
  // band below the axis.
  const totalH = Math.max(88, data.length * rowH + 32);
  const cap = Math.max(1, max ?? data.reduce((m, d) => Math.max(m, d.value), 0));
  const labelPxMap: Record<string, number> = {
    'w-24': 96,
    'w-28': 112,
    'w-32': 128,
    'w-36': 144,
    'w-44': 176,
    'w-48': 192,
    'w-56': 224,
  };
  // Auto-size the label gutter to the longest label so short categories
  // (e.g. 2-letter state codes) don't sit in a wide empty band that pushes the
  // bars toward the center. Pass labelWidth="auto" to force this; an explicit
  // Tailwind width still pins a fixed gutter, and an unknown width falls back
  // to the computed size rather than a large constant.
  const longestLabel = data.reduce(
    (m, d) => Math.max(m, String(typeof d.label === 'string' ? d.label : d.key).length),
    0,
  );
  const autoYWidth = Math.min(200, Math.max(36, Math.round(longestLabel * 7.5) + 14));
  const yWidth = labelWidth === 'auto' ? autoYWidth : labelPxMap[labelWidth] ?? autoYWidth;
  const fmtVal = (v: number) => (unit ? `${Math.round(v)}${unit}` : fmtCount(v));

  // Recharts categorical y-axis needs a string label per row; coerce ReactNode → string.
  const rows = data.map((d) => ({
    ...d,
    name: typeof d.label === 'string' ? d.label : d.key,
    fill: d.color ?? CHART_PALETTE.federalBlue,
  }));

  return (
    <div className={cn('w-full', fill && 'flex min-h-0 flex-1 flex-col', className)}>
      {/* Fill mode: a flex-1 box (min-h-0 so it can size to the flex track)
          with the computed height as a minHeight floor — fills a taller card
          but never collapses to zero. Otherwise a fixed-height box. */}
      <div
        className={cn(fill && 'min-h-0 flex-1')}
        style={fill ? { width: '100%', minHeight: totalH } : { width: '100%', height: totalH }}
      >
        <ResponsiveContainer width="100%" height="100%">
          {/* Visual styling (tick text, grid + axis lines, value labels) lives in
              src/styles/charts.css. Only geometry/behaviour is set via props here:
              bar thickness (barSize) and whole-number ticks (allowDecimals) are SVG
              geometry Recharts computes from props and cannot be set in CSS. */}
          <RBarChart
            layout="vertical"
            data={rows}
            margin={{ top: 4, right: showValueLabels ? 44 : 12, left: 4, bottom: 4 }}
            barCategoryGap="35%"
            className="ccfp-bars"
          >
            <CartesianGrid horizontal={false} strokeDasharray="2 3" />
            <XAxis
              type="number"
              domain={[0, cap]}
              allowDecimals={false}
              tickFormatter={(v: number) => fmtVal(toNum(v))}
            />
            <YAxis type="category" dataKey="name" width={yWidth} tickLine={false} interval={0} />
            <Tooltip
              cursor={{ fill: 'rgba(31,90,168,0.06)' }}
              contentStyle={TOOLTIP_STYLE}
              wrapperStyle={TOOLTIP_WRAPPER_STYLE}
              formatter={(v) => [fmtVal(toNum(v)), 'value']}
            />
            <Bar dataKey="value" radius={[3, 3, 3, 3]} barSize={barSize} isAnimationActive={false}>
              {rows.map((r) => (
                <Cell key={r.key} fill={r.fill} />
              ))}
              {showValueLabels ? (
                <LabelList dataKey="value" position="right" formatter={(v) => fmtVal(toNum(v))} />
              ) : null}
            </Bar>
          </RBarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// StackedHBar — single horizontal bar split into segments
// Implemented with a single-row stacked BarChart for the bar itself, plus a
// React-rendered legend so it stays compact on small cards.
// ──────────────────────────────────────────────────────────────────────────
export function StackedHBar({
  segments,
  total,
  height = 12,
  showLegend = true,
  className,
}: {
  segments: { key: string; label: string; value: number; color?: string }[];
  total?: number;
  height?: number;
  showLegend?: boolean;
  className?: string;
}) {
  const sum = total ?? segments.reduce((s, x) => s + x.value, 0);
  if (sum <= 0) {
    return <div className="text-sm text-muted-foreground">No data.</div>;
  }
  // Build a single record where each segment is its own dataKey.
  const row: Record<string, number> = { _: 0 };
  segments.forEach((s) => {
    row[s.key] = s.value;
  });
  const data = [row];

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div style={{ width: '100%', height: height + 6 }}>
        <ResponsiveContainer width="100%" height="100%">
          <RBarChart layout="vertical" data={data} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <XAxis type="number" hide domain={[0, sum]} />
            <YAxis type="category" hide dataKey="_" />
            <Tooltip
              cursor={{ fill: 'rgba(31,90,168,0.06)' }}
              contentStyle={TOOLTIP_STYLE}
              wrapperStyle={TOOLTIP_WRAPPER_STYLE}
              formatter={(v, name) => {
                const key = String(name ?? '');
                const seg = segments.find((s) => s.key === key);
                return [fmtCount(toNum(v)), seg?.label ?? key];
              }}
            />
            {segments.map((s, i) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                stackId="a"
                fill={s.color ?? SERIES_COLORS[i % SERIES_COLORS.length]}
                isAnimationActive={false}
                radius={
                  i === 0
                    ? [999, 0, 0, 999]
                    : i === segments.length - 1
                      ? [0, 999, 999, 0]
                      : 0
                }
              />
            ))}
          </RBarChart>
        </ResponsiveContainer>
      </div>
      {showLegend ? (
        // Each legend entry is a tight (label + value) pair at natural
        // content width, distributed across the row with `justify-between`
        // so the first entry anchors to the row's left edge (under the
        // first bar segment) and the last anchors to the right edge
        // (under the last bar segment). For 3+ segments the middle
        // entries distribute evenly between, mirroring the bar's
        // left-to-right segment order.
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          {segments.map((s, i) => (
            <LegendDot
              key={s.key}
              color={s.color ?? SERIES_COLORS[i % SERIES_COLORS.length]}
              label={s.label}
              value={fmtCount(s.value)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// VerticalBars — Recharts BarChart with optional grouped series
// ──────────────────────────────────────────────────────────────────────────
export interface VBarSeries {
  key: string;
  label: string;
  color?: string;
  values: number[];
}

export function VerticalBars({
  categories,
  series,
  height = 220,
  showLegend = true,
  yAxisLabel,
  valueFormatter,
  className,
}: {
  categories: string[];
  series: VBarSeries[];
  height?: number;
  showLegend?: boolean;
  yAxisLabel?: React.ReactNode;
  valueFormatter?: (v: number) => string;
  className?: string;
}) {
  if (categories.length === 0) {
    return <div className="text-sm text-muted-foreground">No data.</div>;
  }
  // Pivot categories × series into Recharts-friendly rows.
  const data = categories.map((cat, ci) => {
    const row: Record<string, number | string> = { name: cat };
    for (const s of series) row[s.key] = s.values[ci] ?? 0;
    return row;
  });
  const fmt = valueFormatter ?? fmtCount;
  const yAxisWidth = yAxisLabel ? 64 : 50;
  const leftMargin = yAxisLabel ? 16 : 4;

  return (
    <div className={cn('w-full', className)}>
      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <RBarChart data={data} margin={{ top: 8, right: 12, left: leftMargin, bottom: 4 }}>
            <CartesianGrid stroke={CHART_PALETTE.border} strokeDasharray="2 3" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: '#94A3B8' }}
              stroke={CHART_PALETTE.border}
            />
            <YAxis
              width={yAxisWidth}
              tick={{ fontSize: 10, fill: '#94A3B8' }}
              tickFormatter={(v: number) => fmt(toNum(v))}
              stroke={CHART_PALETTE.border}
              label={
                yAxisLabel
                  ? {
                      value: String(yAxisLabel),
                      angle: -90,
                      position: 'left',
                      offset: 0,
                      style: {
                        fontSize: 10,
                        fill: '#94A3B8',
                        textAnchor: 'middle',
                        letterSpacing: '0.06em',
                      },
                    }
                  : undefined
              }
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              wrapperStyle={TOOLTIP_WRAPPER_STYLE}
              cursor={{ fill: 'rgba(31,90,168,0.06)' }}
              formatter={(v) => fmt(toNum(v))}
            />
            {showLegend ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
            {series.map((s, si) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                fill={s.color ?? SERIES_COLORS[si % SERIES_COLORS.length]}
                radius={[3, 3, 0, 0]}
                isAnimationActive={false}
              />
            ))}
          </RBarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// LineChart — single line + area
// ──────────────────────────────────────────────────────────────────────────
export function LineChart({
  data,
  height = 180,
  color = CHART_PALETTE.federalBlue,
  fillOpacity = 0.18,
  showAxis = true,
  yAxisLabel,
  valueFormatter,
  className,
}: {
  data: { x: string | number; y: number }[];
  height?: number;
  color?: string;
  fillOpacity?: number;
  showAxis?: boolean;
  yAxisLabel?: React.ReactNode;
  /** Format Y-axis ticks + tooltip values. Defaults to thousands-separated count. */
  valueFormatter?: (v: number) => string;
  className?: string;
}) {
  if (data.length === 0) {
    return <div className="text-sm text-muted-foreground">No data.</div>;
  }
  const rows = data.map((d) => ({ name: String(d.x), y: d.y }));
  const gradId = React.useId().replace(/[:]/g, '');
  const fmt = valueFormatter ?? fmtCount;
  // When the Y-axis label is present we widen the YAxis area so the
  // rotated label sits flush against the left edge without overlapping
  // tick numbers.
  const yAxisWidth = showAxis ? (yAxisLabel ? 64 : 50) : 0;
  const leftMargin = showAxis ? (yAxisLabel ? 16 : 4) : 0;

  return (
    <div className={cn('w-full', className)}>
      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <RAreaChart
            data={rows}
            margin={{ top: 8, right: 8, left: leftMargin, bottom: 4 }}
          >
            <defs>
              <linearGradient id={`g-${gradId}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={fillOpacity * 1.4} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={CHART_PALETTE.border} strokeDasharray="2 3" />
            {showAxis ? (
              <XAxis
                dataKey="name"
                tick={{ fontSize: 10, fill: '#94A3B8' }}
                stroke={CHART_PALETTE.border}
              />
            ) : (
              <XAxis dataKey="name" hide />
            )}
            {showAxis ? (
              <YAxis
                width={yAxisWidth}
                tick={{ fontSize: 10, fill: '#94A3B8' }}
                tickFormatter={(v: number) => fmt(toNum(v))}
                stroke={CHART_PALETTE.border}
                label={
                  yAxisLabel
                    ? {
                        value: String(yAxisLabel),
                        angle: -90,
                        position: 'left',
                        offset: 0,
                        style: {
                          fontSize: 10,
                          fill: '#94A3B8',
                          textAnchor: 'middle',
                          letterSpacing: '0.06em',
                        },
                      }
                    : undefined
                }
              />
            ) : (
              <YAxis hide />
            )}
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              wrapperStyle={TOOLTIP_WRAPPER_STYLE}
              formatter={(v) => [fmt(toNum(v)), '']}
            />
            <Area
              type="monotone"
              dataKey="y"
              stroke={color}
              strokeWidth={2}
              fill={`url(#g-${gradId})`}
              dot={{ r: 2.5, fill: color, strokeWidth: 0 }}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
          </RAreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// MultiLineChart — multi-series line trend
// ──────────────────────────────────────────────────────────────────────────
export interface LineSeries {
  key: string;
  label: string;
  color?: string;
  values: number[];
}

export function MultiLineChart({
  categories,
  series,
  height = 220,
  showLegend = true,
  yAxisLabel,
  valueFormatter,
  className,
}: {
  categories: (string | number)[];
  series: LineSeries[];
  height?: number;
  showLegend?: boolean;
  yAxisLabel?: React.ReactNode;
  valueFormatter?: (v: number) => string;
  className?: string;
}) {
  if (categories.length === 0) {
    return <div className="text-sm text-muted-foreground">No data.</div>;
  }
  const data = categories.map((c, i) => {
    const row: Record<string, number | string> = { name: String(c) };
    for (const s of series) row[s.key] = s.values[i] ?? 0;
    return row;
  });
  const fmt = valueFormatter ?? fmtCount;
  const yAxisWidth = yAxisLabel ? 64 : 50;
  const leftMargin = yAxisLabel ? 16 : 4;

  return (
    <div className={cn('w-full', className)}>
      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <RLineChart data={data} margin={{ top: 8, right: 12, left: leftMargin, bottom: 4 }}>
            <CartesianGrid stroke={CHART_PALETTE.border} strokeDasharray="2 3" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: '#94A3B8' }}
              stroke={CHART_PALETTE.border}
            />
            <YAxis
              width={yAxisWidth}
              tick={{ fontSize: 10, fill: '#94A3B8' }}
              tickFormatter={(v: number) => fmt(toNum(v))}
              stroke={CHART_PALETTE.border}
              label={
                yAxisLabel
                  ? {
                      value: String(yAxisLabel),
                      angle: -90,
                      position: 'left',
                      offset: 0,
                      style: {
                        fontSize: 10,
                        fill: '#94A3B8',
                        textAnchor: 'middle',
                        letterSpacing: '0.06em',
                      },
                    }
                  : undefined
              }
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              wrapperStyle={TOOLTIP_WRAPPER_STYLE}
              formatter={(v) => fmt(toNum(v))}
            />
            {showLegend ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
            {series.map((s, si) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color ?? SERIES_COLORS[si % SERIES_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 2.4 }}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            ))}
          </RLineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Sparkline — tiny inline trend
// ──────────────────────────────────────────────────────────────────────────
export function Sparkline({
  values,
  width = 96,
  height = 28,
  color = CHART_PALETTE.federalBlue,
  className,
}: {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  className?: string;
}) {
  if (values.length === 0) {
    return <div className={cn('text-2xs text-muted-foreground', className)}>—</div>;
  }
  const data = values.map((v, i) => ({ name: String(i), y: v }));
  return (
    <div className={className} style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RLineChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <Line
            type="monotone"
            dataKey="y"
            stroke={color}
            strokeWidth={1.6}
            dot={false}
            activeDot={{ r: 2.5 }}
            isAnimationActive={false}
          />
        </RLineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// GaugeArc — built on Recharts <RadialBarChart> with a 180° sweep
// ──────────────────────────────────────────────────────────────────────────
export function GaugeArc({
  value,
  max = 100,
  size = 160,
  thickness = 18,
  color,
  label,
  formatValue,
  className,
}: {
  value: number;
  max?: number;
  size?: number;
  thickness?: number;
  color?: string;
  label?: React.ReactNode;
  formatValue?: (v: number) => string;
  className?: string;
}) {
  const ratio = Math.max(0, Math.min(1, value / max));
  const colorVal =
    color ??
    (ratio < 0.34
      ? CHART_PALETTE.alertRed
      : ratio < 0.67
        ? CHART_PALETTE.alertAmber
        : CHART_PALETTE.successGreen);
  const fmt = formatValue ?? ((v: number) => `${Math.round((v / max) * 100)}%`);

  // Half-circle gauge: startAngle 180 → endAngle 0 sweeps the top half.
  // The chart container reserves a dedicated band below the arc for the
  // value label, and the arc's center (cy) is anchored at the bottom of
  // the arc area — NOT the bottom of the container — so the curve never
  // intrudes into the text band. Using pixel radii (rather than %) keeps
  // the arc at its full intended size regardless of container aspect.
  const data = [{ name: 'value', value }];
  const arcHeight = size / 2;
  const valueAreaHeight = 26;
  const totalHeight = arcHeight + valueAreaHeight;

  return (
    <div className={cn('flex flex-col items-center', className)}>
      <div style={{ width: size, height: totalHeight }} className="relative">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            startAngle={180}
            endAngle={0}
            innerRadius={size / 2 - thickness - 2}
            outerRadius={size / 2}
            data={data}
            cx="50%"
            cy={arcHeight}
          >
            <PolarAngleAxis type="number" domain={[0, max]} tick={false} />
            <RadialBar
              dataKey="value"
              cornerRadius={4}
              fill={colorVal}
              background={{ fill: CHART_PALETTE.border }}
              isAnimationActive={false}
            />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-x-0 bottom-1 flex justify-center">
          <span className="text-base font-bold leading-none text-foreground">
            {fmt(value)}
          </span>
        </div>
      </div>
      {label ? <div className="mt-1 text-2xs text-muted-foreground">{label}</div> : null}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// FunnelChart — Recharts <Funnel>
// ──────────────────────────────────────────────────────────────────────────
export interface FunnelStage {
  key: string;
  label: string;
  value: number;
  color?: string;
}

export function FunnelChart({
  stages,
  height = 220,
  className,
}: {
  stages: FunnelStage[];
  height?: number;
  className?: string;
}) {
  if (stages.length === 0) {
    return <div className="text-sm text-muted-foreground">No data.</div>;
  }
  const data = stages.map((s, i) => ({
    name: s.label,
    value: s.value,
    fill: s.color ?? SERIES_COLORS[i % SERIES_COLORS.length],
  }));

  return (
    <div className={cn('w-full', className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RFunnelChart>
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            wrapperStyle={TOOLTIP_WRAPPER_STYLE}
            formatter={(v) => fmtCount(toNum(v))}
          />
          <Funnel dataKey="value" data={data} isAnimationActive={false}>
            <LabelList
              position="right"
              fill="#1F2937"
              stroke="none"
              dataKey="name"
              style={{ fontSize: 11, fontWeight: 600 }}
              formatter={(name) => {
                const key = String(name ?? '');
                const stage = data.find((s) => s.name === key);
                return stage ? `${key} — ${fmtCount(stage.value)}` : key;
              }}
            />
          </Funnel>
        </RFunnelChart>
      </ResponsiveContainer>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// HeatmapMatrix — Recharts has no native heatmap, so we render the grid
// using a lightweight SVG (still matches the federal palette) with tooltips
// via native <title>. Kept here for API parity.
// ──────────────────────────────────────────────────────────────────────────
export function HeatmapMatrix({
  rows,
  rowLabels,
  columnLabels,
  height = 160,
  className,
  colorScale,
  emptyColor = CHART_PALETTE.border,
  hint,
}: {
  rows: number[][];
  rowLabels: string[];
  columnLabels: string[];
  height?: number;
  className?: string;
  colorScale?: (intensity: number) => string;
  emptyColor?: string;
  hint?: (row: string, col: string, value: number) => React.ReactNode;
}) {
  if (rows.length === 0 || columnLabels.length === 0) {
    return <div className="text-sm text-muted-foreground">No data.</div>;
  }
  const W = 640;
  const H = height;
  const padL = 90;
  const padR = 8;
  const padT = 24;
  const padB = 6;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const cellW = innerW / columnLabels.length;
  const cellH = innerH / rows.length;
  let max = 0;
  for (const r of rows) for (const v of r) if (v > max) max = v;
  max = Math.max(1, max);

  const scale =
    colorScale ??
    ((intensity: number) => {
      if (intensity <= 0) return emptyColor;
      const t = intensity;
      const r = Math.round(255 + (31 - 255) * t);
      const g = Math.round(255 + (90 - 255) * t);
      const b = Math.round(255 + (168 - 255) * t);
      return `rgb(${r}, ${g}, ${b})`;
    });

  return (
    <div className={cn('w-full', className)}>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img" style={{ minHeight: height }}>
        {columnLabels.map((c, i) => (
          <text
            key={c}
            x={padL + cellW * (i + 0.5)}
            y={padT - 8}
            textAnchor="middle"
            style={{ font: '500 10px var(--font-sans, system-ui)' }}
            className="fill-muted-foreground"
          >
            {c}
          </text>
        ))}
        {rowLabels.map((r, ri) => (
          <text
            key={r}
            x={padL - 8}
            y={padT + cellH * (ri + 0.5) + 3}
            textAnchor="end"
            style={{ font: '500 10px var(--font-sans, system-ui)' }}
            className="fill-foreground"
          >
            {r}
          </text>
        ))}
        {rows.map((row, ri) =>
          row.map((v, ci) => {
            const intensity = v / max;
            return (
              <rect
                key={`${ri}-${ci}`}
                x={padL + cellW * ci + 1}
                y={padT + cellH * ri + 1}
                width={Math.max(2, cellW - 2)}
                height={Math.max(2, cellH - 2)}
                fill={scale(intensity)}
                stroke={CHART_PALETTE.card}
              >
                <title>{hint ? hint(rowLabels[ri], columnLabels[ci], v) : `${v}`}</title>
              </rect>
            );
          }),
        )}
      </svg>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// ProgressMeter — labeled progress bar with value display.
// Kept Tailwind-rendered (a chart library is overkill for a 2-px bar).
// ──────────────────────────────────────────────────────────────────────────
export function ProgressMeter({
  value,
  max,
  label,
  hint,
  color = CHART_PALETTE.federalBlue,
  className,
  formatValue,
}: {
  value: number;
  max: number;
  label?: React.ReactNode;
  hint?: React.ReactNode;
  color?: string;
  className?: string;
  formatValue?: (v: number, max: number) => React.ReactNode;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      {(label || formatValue) && (
        <div className="flex items-baseline justify-between gap-2 text-xs">
          {label ? <span className="text-foreground">{label}</span> : <span />}
          <span className="tabular-nums font-medium text-foreground">
            {formatValue
              ? formatValue(value, max)
              : `${fmtCount(value)} / ${fmtCount(max)}`}
          </span>
        </div>
      )}
      <div className="relative h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      {hint ? <div className="text-2xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}
