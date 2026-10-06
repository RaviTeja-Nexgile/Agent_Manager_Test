import * as React from 'react';

export interface UseApiState<T> {
  data: T | undefined;
  loading: boolean;
  error: Error | null;
  reload: () => void;
}

/**
 * Tiny data hook. Calls the supplied loader on mount + when `deps` change.
 * Returns loading / data / error and a manual reload trigger.
 */
export function useApi<T>(
  loader: () => Promise<T>,
  deps: React.DependencyList = [],
): UseApiState<T> {
  const [data, setData] = React.useState<T>();
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);
  const [tick, setTick] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loader()
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = React.useCallback(() => setTick((t) => t + 1), []);

  return { data, loading, error, reload };
}
