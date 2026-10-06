import * as React from 'react';
import { ChevronDown, Landmark, Lock } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * U.S. government banner (federal website standard, project_documentation §14.1).
 *
 * A thin full-width strip reading "An official website of the United States
 * government" with an accessible "Here's how you know" expander explaining the
 * `.gov` domain and HTTPS. Built as a self-contained Tailwind component (no
 * USWDS npm dependency) and mounted on every official surface: the app shell,
 * the login page, and the public-outputs page.
 *
 * Accessibility (Section 508 / WCAG 2.1 AA): the toggle is a real `<button>`
 * with `aria-expanded` / `aria-controls`; the explainer panel is collapsed by
 * default and keyboard-reachable.
 */
export interface GovBannerProps {
  className?: string;
}

export function GovBanner({ className }: GovBannerProps) {
  const [open, setOpen] = React.useState(false);
  const panelId = React.useId();
  const wrapRef = React.useRef<HTMLDivElement>(null);

  // Dismiss the dropdown on outside click or Escape (Section 508 keyboard support).
  React.useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  return (
    <div
      className={cn(
        'w-full border-b border-neutral-base-200 bg-neutral-base-50 text-neutral-base-700',
        className,
      )}
    >
      <div className="mx-auto flex max-w-screen-2xl flex-wrap items-center gap-x-2 gap-y-1 px-4 py-1 text-xs sm:px-6">
        <Landmark className="h-3.5 w-3.5 shrink-0 text-neutral-base-500" aria-hidden="true" />
        <span className="text-neutral-base-700">
          An official website of the United States government
        </span>

        {/* Anchored to the right corner; the explainer opens as a right-aligned dropdown. */}
        <div className="relative ml-auto" ref={wrapRef}>
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-controls={panelId}
            className="inline-flex items-center gap-0.5 rounded-sm font-medium text-federal-blue underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-federal-blue focus-visible:ring-offset-1"
          >
            Here&rsquo;s how you know
            <ChevronDown
              className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')}
              aria-hidden="true"
            />
          </button>

          {open ? (
            <div
              id={panelId}
              className="absolute right-0 z-50 mt-2 w-[min(40rem,calc(100vw-2rem))] rounded-lg border border-neutral-base-200 bg-white p-4 shadow-lg"
            >
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="flex items-start gap-3">
                  <Landmark
                    className="mt-0.5 h-5 w-5 shrink-0 text-neutral-base-500"
                    aria-hidden="true"
                  />
                  <p className="text-xs leading-relaxed text-neutral-base-700">
                    <strong className="font-semibold">Official websites use .gov</strong>
                    <br />A <strong className="font-semibold">.gov</strong> website belongs to an
                    official government organization in the United States.
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <Lock
                    className="mt-0.5 h-5 w-5 shrink-0 text-neutral-base-500"
                    aria-hidden="true"
                  />
                  <p className="text-xs leading-relaxed text-neutral-base-700">
                    <strong className="font-semibold">Secure .gov websites use HTTPS</strong>
                    <br />A <strong className="font-semibold">lock</strong> (
                    <Lock className="inline h-3 w-3 align-text-bottom" aria-hidden="true" />) or{' '}
                    <strong className="font-semibold">https://</strong> means you&rsquo;ve safely
                    connected to the .gov website. Share sensitive information only on official,
                    secure websites.
                  </p>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
