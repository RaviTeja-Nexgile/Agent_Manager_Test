import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

/**
 * Recover from a stale app shell after a release.
 *
 * Routes are lazily imported, so the shell references chunk filenames by
 * content hash. A device that precached the shell before a deploy keeps asking
 * for the *old* hashes, which no longer exist on the server — the import
 * rejects and React Router renders "Unexpected Application Error" over a blank
 * page. The service worker does fetch the new shell, but only after the current
 * page has already failed.
 *
 * That failure mode is unacceptable for the roadside case this app exists to
 * serve: an inspector opening a phone at a crash scene sees a white screen and
 * has no way to know a reload would fix it. Reloading for them costs one
 * navigation and picks up the shell the new worker already installed.
 *
 * Guarded so a chunk that is genuinely gone degrades to the error screen instead
 * of reloading forever. The guard is time-windowed rather than cleared on mount:
 * `render()` only *schedules* the tree, so a flag cleared on the next line would
 * always be gone by the time a lazy route actually failed — which is to say it
 * would never suppress anything, and the page would reload in a tight loop. A
 * repeat failure within the window is that loop and is left alone; a failure
 * long afterwards is a fresh deploy and earns a new attempt.
 */
const STALE_SHELL_KEY = 'ccfp.stale-shell-reload';
const STALE_SHELL_WINDOW_MS = 60_000;

function recoverFromStaleShell(reason: string): void {
  const now = Date.now();
  try {
    const prev = JSON.parse(sessionStorage.getItem(STALE_SHELL_KEY) || '{}') as {
      at?: number;
    };
    // Still inside the window means the reload we already performed did not
    // help. Stop, and let the error screen say so.
    if (typeof prev.at === 'number' && now - prev.at < STALE_SHELL_WINDOW_MS) return;
    sessionStorage.setItem(STALE_SHELL_KEY, JSON.stringify({ at: now, reason }));
  } catch {
    return; // no sessionStorage (private mode) — never risk a reload loop
  }
  window.location.reload();
}

// Vite dispatches this when a lazily-imported chunk cannot be fetched.
window.addEventListener('vite:preloadError', (e) => {
  e.preventDefault();
  recoverFromStaleShell('preload');
});

// The import() itself can also reject without a preload event — same cause,
// same remedy. Matched on the message because no typed error is thrown.
window.addEventListener('unhandledrejection', (e) => {
  const msg = String((e.reason as Error)?.message ?? e.reason ?? '');
  if (/dynamically imported module|Importing a module script failed/i.test(msg)) {
    recoverFromStaleShell('import');
  }
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
