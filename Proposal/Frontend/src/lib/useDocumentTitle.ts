import { useEffect } from 'react';

/**
 * Federal website standard (§14.1) — descriptive per-page titles.
 *
 * Sets `document.title` to `${title} · CCFP` (or just `CCFP` when no title is
 * given) so each route has a distinct, descriptive title for the browser tab,
 * history, and screen readers. Keyed on `title`; the next page sets its own,
 * so no cleanup is needed on unmount.
 *
 * Routed pages mounted inside the app shell get their titles from React Router
 * route `handle.title` (see `AppShell`); standalone surfaces such as the login
 * and public pages call this hook directly.
 */
export const TITLE_SUFFIX = 'CCFP';

export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = title ? `${title} · ${TITLE_SUFFIX}` : TITLE_SUFFIX;
  }, [title]);
}
