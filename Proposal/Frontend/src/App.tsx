import { Suspense } from 'react';
import { RouterProvider } from 'react-router-dom';
import { router } from './app/router';
import { AuthProvider } from './app/auth';
import { OfflineProvider } from './lib/offline/useOffline';

export default function App() {
  return (
    <AuthProvider>
      {/* Connectivity + outbox state. Sits inside AuthProvider because replay
          needs the access token, and outside the router so the pending count
          survives navigation. */}
      <OfflineProvider>
        <Suspense
          fallback={
            <div className="flex h-screen items-center justify-center bg-muted/30">
              <div className="text-sm text-muted-foreground">Loading…</div>
            </div>
          }
        >
          <RouterProvider router={router} />
        </Suspense>
      </OfflineProvider>
    </AuthProvider>
  );
}
