import * as React from 'react';
import { useOutletContext } from 'react-router-dom';
import type { Crash } from '@/lib/types';

export interface CrashContextValue {
  crash: Crash;
  reload: () => void;
}

/** Provided by CrashDetailPage via <Outlet context=...>. */
export function useCrash(): CrashContextValue {
  return useOutletContext<CrashContextValue>();
}
