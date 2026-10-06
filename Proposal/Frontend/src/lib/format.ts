/** Money/number/date/text formatting helpers. */

export function formatNumber(n: number | string | null | undefined): string {
  if (n === null || n === undefined || n === '') return '—';
  const v = typeof n === 'string' ? Number(n) : n;
  if (Number.isNaN(v)) return '—';
  return new Intl.NumberFormat('en-US').format(v);
}

export function formatPercent(
  pct: number | string | null | undefined,
  digits = 1,
): string {
  if (pct === null || pct === undefined || pct === '') return '—';
  const n = typeof pct === 'string' ? Number(pct) : pct;
  if (Number.isNaN(n)) return '—';
  return `${n.toFixed(digits)}%`;
}

export function formatDate(
  iso: string | null | undefined,
  opts: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'short', day: 'numeric' },
): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('en-US', opts).format(d);
}

export function formatDateTime(iso: string | null | undefined): string {
  return formatDate(iso, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return '—';
  const now = Date.now();
  const diffSec = Math.round((d - now) / 1000);
  const abs = Math.abs(diffSec);
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  if (abs < 60) return rtf.format(diffSec, 'second');
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), 'hour');
  if (abs < 30 * 86400) return rtf.format(Math.round(diffSec / 86400), 'day');
  if (abs < 365 * 86400) return rtf.format(Math.round(diffSec / (30 * 86400)), 'month');
  return rtf.format(Math.round(diffSec / (365 * 86400)), 'year');
}

/** Title-case a snake_case / SCREAMING_CASE / kebab-case string. */
export function humanize(s: string | null | undefined): string {
  if (!s) return '';
  return s
    .toLowerCase()
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Compress a UUID into the first 8 chars for display. */
export function shortId(id: string | null | undefined): string {
  if (!id) return '—';
  return id.slice(0, 8);
}

/** A short 12-hour time with an AM/PM indicator like "6:45 AM". Accepts "HH:MM:SS" or "HH:MM". */
export function formatTime(t: string | null | undefined): string {
  if (!t) return '—';
  const [h, m] = t.split(':');
  if (h === undefined || m === undefined) return t;
  const hour = Number(h);
  if (Number.isNaN(hour)) return t;
  const ampm = hour < 12 ? 'AM' : 'PM';
  const h12 = ((hour + 11) % 12) + 1;
  return `${h12}:${m.padStart(2, '0')} ${ampm}`;
}
