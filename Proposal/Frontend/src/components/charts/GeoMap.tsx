import * as React from 'react';

/**
 * Geospatial visualization for CCFP (GAP-BRD-11).
 *
 * WHY NOT A GEOJSON CHOROPLETH. The gap analysis recommends a bundled
 * state-outline GeoJSON. That is the right long-term shape, but it requires
 * authoritative boundary data (Census TIGER/cartographic files) that must be
 * vendored deliberately, not reconstructed — approximated coastlines drawn from
 * memory would be worse than no map, because a map asserts geographic fact.
 *
 * This renders what CAN be plotted honestly today: an equirectangular
 * projection of REAL coordinates — the crash `latitude`/`longitude` the gap
 * notes were "captured and editable but rendered only as text fields and never
 * plotted" — with State positions from published centroids for the aggregate
 * view. Centroids are approximate BY DEFINITION, so error degrades gracefully;
 * a polygon that is wrong is simply wrong.
 *
 * Deployment posture (documentation §16, .gov/CSP): no tile server, no external
 * host, no network request of any kind. Pure inline SVG.
 *
 * Swapping in real boundaries later means replacing `UsFrame` with vendored
 * polygons — the projection, scales, colors, and interaction below are
 * unchanged by that.
 */

// ── Sequential ramp ────────────────────────────────────────────────────────
// Magnitude ⇒ ONE hue, light→dark. Both ramps are validated with the dataviz
// skill's `validateOrdinal`: lightness monotone, adjacent ΔL ≥ 0.06, single hue
// (≤3° spread), and light-end contrast ≥ 2:1 against their own surface. Dark
// mode is a SELECTED set of steps against the dark surface, not a flipped copy.
export const SEQ_RAMP_LIGHT = ['#9DB9DD', '#7599C9', '#4E78B2', '#2A5793', '#143B71'] as const;
export const SEQ_RAMP_DARK = ['#36547F', '#456FA6', '#5B8AC9', '#82ACDA', '#B0CBEA'] as const;

/** Approximate State centroids (lat, lon). Used only to position aggregates. */
const STATE_CENTROIDS: Record<string, [number, number]> = {
  AL: [32.8, -86.8], AK: [64.0, -152.0], AZ: [34.3, -111.7], AR: [34.9, -92.4],
  CA: [37.2, -119.5], CO: [39.0, -105.5], CT: [41.6, -72.7], DE: [39.0, -75.5],
  DC: [38.9, -77.0], FL: [28.6, -82.4], GA: [32.6, -83.4], HI: [20.3, -156.4],
  ID: [44.4, -114.6], IL: [40.0, -89.2], IN: [39.9, -86.3], IA: [42.1, -93.5],
  KS: [38.5, -98.4], KY: [37.5, -85.3], LA: [31.0, -92.0], ME: [45.4, -69.2],
  MD: [39.0, -76.8], MA: [42.3, -71.8], MI: [44.3, -85.4], MN: [46.3, -94.3],
  MS: [32.7, -89.7], MO: [38.4, -92.5], MT: [47.0, -109.6], NE: [41.5, -99.8],
  NV: [39.3, -116.6], NH: [43.7, -71.6], NJ: [40.2, -74.7], NM: [34.4, -106.1],
  NY: [42.9, -75.5], NC: [35.5, -79.4], ND: [47.4, -100.5], OH: [40.3, -82.8],
  OK: [35.6, -97.5], OR: [43.9, -120.6], PA: [40.9, -77.8], RI: [41.7, -71.6],
  SC: [33.9, -80.9], SD: [44.4, -100.2], TN: [35.8, -86.3], TX: [31.5, -99.3],
  UT: [39.3, -111.7], VT: [44.1, -72.7], VA: [37.5, -78.9], WA: [47.4, -120.4],
  WV: [38.6, -80.6], WI: [44.6, -89.7], WY: [43.0, -107.6],
  PR: [18.2, -66.4], GU: [13.4, 144.8], VI: [18.0, -64.8],
};

/** Continental US viewport. Alaska/Hawaii/territories are listed separately. */
const BOUNDS = { minLon: -125, maxLon: -66.5, minLat: 24, maxLat: 49.5 };

interface GeoDatum {
  /** Two-letter State code, for the aggregate view. */
  key: string;
  label: string;
  value: number;
}
export interface GeoPointDatum {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  value?: number | null;
  sublabel?: string | null;
}

function useRamp(): readonly string[] {
  // Match the viewer's theme; the dark ramp is its own validated set of steps.
  const [dark, setDark] = React.useState(false);
  React.useEffect(() => {
    const check = () => {
      const attr = document.documentElement.getAttribute('data-theme');
      setDark(attr === 'dark' || (!attr && window.matchMedia?.('(prefers-color-scheme: dark)').matches));
    };
    check();
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    mq?.addEventListener?.('change', check);
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => { mq?.removeEventListener?.('change', check); obs.disconnect(); };
  }, []);
  return dark ? SEQ_RAMP_DARK : SEQ_RAMP_LIGHT;
}

/**
 * Bucket a value onto the ramp. Quantile-ish via equal steps over the observed
 * range — with a guard for the all-equal case, where every bucket would
 * otherwise collapse to index 0 and the map would read as "no data anywhere".
 */
function bucket(value: number, max: number, steps: number): number {
  if (max <= 0) return 0;
  const i = Math.ceil((value / max) * steps) - 1;
  return Math.min(steps - 1, Math.max(0, i));
}

const project = (lat: number, lon: number, w: number, h: number) => ({
  x: ((lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon)) * w,
  // SVG y grows downward; latitude grows northward — hence the inversion.
  y: h - ((lat - BOUNDS.minLat) / (BOUNDS.maxLat - BOUNDS.minLat)) * h,
});

/** A recessive outline of the continental US bounding frame + a lat/lon graticule. */
function UsFrame({ w, h }: { w: number; h: number }) {
  const lons = [-120, -110, -100, -90, -80, -70];
  const lats = [25, 30, 35, 40, 45];
  return (
    <g aria-hidden="true">
      <rect x={0} y={0} width={w} height={h} rx={6} className="fill-muted/25 stroke-border" strokeWidth={1} />
      {lons.map((lon) => {
        const { x } = project(0, lon, w, h);
        return <line key={`lon${lon}`} x1={x} y1={0} x2={x} y2={h} className="stroke-border" strokeWidth={0.5} strokeDasharray="2 4" />;
      })}
      {lats.map((lat) => {
        const { y } = project(lat, 0, w, h);
        return <line key={`lat${lat}`} x1={0} y1={y} x2={w} y2={y} className="stroke-border" strokeWidth={0.5} strokeDasharray="2 4" />;
      })}
    </g>
  );
}

/**
 * Proportional-symbol map of a per-State measure, plus optional individual
 * crash points. Hover is shipped by default (an SVG chart IS interactive), and
 * a table view is always available so identity is never colour-alone.
 */
export function GeoMap({
  data = [],
  points = [],
  valueLabel = 'Crashes',
  height = 420,
  showPoints = false,
}: {
  data?: GeoDatum[];
  points?: GeoPointDatum[];
  valueLabel?: string;
  height?: number;
  showPoints?: boolean;
}) {
  const ramp = useRamp();
  const W = 760;
  const H = height;
  const [hover, setHover] = React.useState<{ x: number; y: number; title: string; body: string } | null>(null);

  const max = React.useMemo(() => Math.max(0, ...data.map((d) => d.value)), [data]);
  const offscreen = data.filter((d) => !STATE_CENTROIDS[d.key]);
  const outsideFrame = data.filter(
    (d) => STATE_CENTROIDS[d.key] &&
      (STATE_CENTROIDS[d.key][1] < BOUNDS.minLon || STATE_CENTROIDS[d.key][1] > BOUNDS.maxLon ||
       STATE_CENTROIDS[d.key][0] < BOUNDS.minLat || STATE_CENTROIDS[d.key][0] > BOUNDS.maxLat),
  );
  const plottable = data.filter((d) => STATE_CENTROIDS[d.key] && !outsideFrame.includes(d));

  // Radius by sqrt of value so AREA encodes magnitude — sizing by radius would
  // overstate large values roughly quadratically.
  const radius = (v: number) => (max <= 0 ? 6 : 6 + Math.sqrt(v / max) * 20);

  return (
    <div className="space-y-3">
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          role="img"
          aria-label={`Map of ${valueLabel.toLowerCase()} by location. ${plottable.length} States plotted. A table of the same figures follows.`}
        >
          <UsFrame w={W} h={H} />

          {/* Individual crash positions — the real lat/long the gap notes were
              never plotted. Drawn beneath the aggregates so a dense cluster
              cannot hide a State total. */}
          {showPoints && points.map((p) => {
            const { x, y } = project(p.latitude, p.longitude, W, H);
            if (x < 0 || x > W || y < 0 || y > H) return null;
            const enter = () => setHover({
              x, y, title: p.label,
              body: `${p.sublabel ?? ''}${p.value != null ? ` · ${p.value} fatalities` : ''}`.trim(),
            });
            return (
              <g key={p.id}>
                <circle
                  cx={x} cy={y} r={3.5}
                  className="fill-foreground/45 stroke-background"
                  strokeWidth={1}
                  pointerEvents="none"
                />
                {/* Invisible hit target: a 3.5px mark is far below a usable
                    pointer target, so the mark is drawn small and hovered big. */}
                <circle
                  cx={x} cy={y} r={9}
                  fill="transparent"
                  onMouseEnter={enter}
                  onMouseLeave={() => setHover(null)}
                />
              </g>
            );
          })}

          {plottable.map((d) => {
            const [lat, lon] = STATE_CENTROIDS[d.key];
            const { x, y } = project(lat, lon, W, H);
            const r = radius(d.value);
            const fill = ramp[bucket(d.value, max, ramp.length)];
            return (
              <g key={d.key}>
                {/* 2px surface ring so overlapping symbols stay separable. */}
                <circle
                  cx={x} cy={y} r={r}
                  fill={fill}
                  className="stroke-background"
                  strokeWidth={2}
                  opacity={0.92}
                  onMouseEnter={() => setHover({ x, y, title: d.label, body: `${d.value} ${valueLabel.toLowerCase()}` })}
                  onMouseLeave={() => setHover(null)}
                />
                {/* Direct-label only the largest few — never a number on every mark.
                    pointerEvents="none" is load-bearing: without it the label sits
                    on top of its own circle's centre and swallows the pointer, so
                    hovering the middle of the LARGEST symbol — the one a reader
                    reaches for first — yields no tooltip. Same for the State
                    abbreviation below the mark. */}
                {d.value >= max * 0.6 && r > 12 ? (
                  <text
                    x={x} y={y + 4} textAnchor="middle"
                    pointerEvents="none"
                    className="fill-background text-[11px] font-semibold tabular-nums"
                  >
                    {d.value}
                  </text>
                ) : null}
                <text
                  x={x} y={y + r + 11} textAnchor="middle"
                  pointerEvents="none"
                  className="fill-muted-foreground text-[10px] font-medium"
                >
                  {d.key}
                </text>
              </g>
            );
          })}
        </svg>

        {hover ? (
          <div
            className="pointer-events-none absolute z-10 rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs shadow-md"
            style={{ left: `${(hover.x / W) * 100}%`, top: `${(hover.y / H) * 100}%`, transform: 'translate(-50%, -130%)' }}
            role="status"
          >
            <div className="font-medium">{hover.title}</div>
            {hover.body ? <div className="text-muted-foreground">{hover.body}</div> : null}
          </div>
        ) : null}
      </div>

      {/* Legend: the ramp is the only carrier of magnitude, so it is always shown. */}
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span>{valueLabel}</span>
        <span className="inline-flex items-center gap-1">
          <span>0</span>
          {ramp.map((c) => (
            <span key={c} className="inline-block h-3 w-6 first:rounded-l last:rounded-r" style={{ backgroundColor: c }} />
          ))}
          <span className="tabular-nums">{max}</span>
        </span>
        {showPoints && points.length ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-foreground/45" />
            individual crash location
          </span>
        ) : null}
      </div>

      {/* Anything the frame cannot show is stated, not dropped — a map that
          silently omits Alaska reads as "no crashes in Alaska". */}
      {(offscreen.length > 0 || outsideFrame.length > 0) ? (
        <p className="text-xs text-muted-foreground">
          Outside the continental frame:{' '}
          {[...outsideFrame, ...offscreen].map((d) => `${d.key} (${d.value})`).join(', ')} — included in the
          table below.
        </p>
      ) : null}
    </div>
  );
}
