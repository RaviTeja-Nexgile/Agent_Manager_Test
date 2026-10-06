import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import path from 'node:path';

export default defineConfig({
  plugins: [
    react(),
    /**
     * Service worker — the half of "offline-first" that IndexedDB cannot do.
     *
     * The outbox and read cache only help a tab that is already running. An
     * MCSAP inspector arriving at a crash scene opens the app cold, and without
     * a precached shell the browser cannot fetch index.html or the bundle, so
     * none of the offline code is ever reached. Precaching the shell is what
     * makes the Initial Incident Form reachable with no connectivity.
     */
    VitePWA({
      // Ship fixes without asking a user standing at a crash scene to reload.
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'CCFP · Crash Causal Factors Program',
        short_name: 'CCFP',
        description:
          'FMCSA Crash Causal Factors Program — crash data collection, quality control and analysis.',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: '#FFFFFF',
        theme_color: '#0F2A4A',
        icons: [
          {
            src: '/favicon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any',
          },
        ],
      },
      workbox: {
        // Fonts are bundled by @fontsource, so they land in dist/assets and are
        // caught here; a shell that renders without its typeface is not the
        // Section 508 experience the online app was reviewed against.
        globPatterns: ['**/*.{js,css,html,svg,woff,woff2,ico,png}'],
        // Deep links are the normal entry point — an inspector opens the app on
        // /crashes/<id>. Without this, any route but "/" 404s on a cold offline
        // start because no such file was ever precached.
        navigateFallback: '/index.html',
        // ...but never answer an API call with the HTML shell. A JSON caller
        // receiving markup fails in a far more confusing way than a clean
        // network error, and api.ts already has a cache path for reads.
        navigateFallbackDenylist: [/^\/api\//],
        /**
         * Deliberately NO runtimeCaching for /api.
         *
         * Crash reads carry PII and CIPSEA-protected interview data. The app
         * caches those itself in IndexedDB under a key namespaced by user id,
         * and clears that store on every session teardown (app/auth.tsx). A
         * Workbox runtime cache would put the same PII in Cache Storage, which
         * that teardown does not touch — leaving one user's crash data readable
         * to whoever signs in next on a shared field device. The shell is
         * precached; the data stays in the store that knows how to forget it.
         */
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        skipWaiting: true,
        // The charts vendor chunk exceeds the 2 MiB default; without this it is
        // silently dropped from the precache and the shell breaks offline.
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
      },
      // The dev server has no precache, so `npm run dev` behaves exactly as it
      // always has. Verify offline behaviour against `npm run build` + preview,
      // which is the artifact that actually ships.
      devOptions: { enabled: false },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
    },
  },
  // The offline path can only be exercised against a real build, so preview
  // needs the same API proxy the dev server has.
  preview: {
    port: 4173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'icons-vendor': ['lucide-react'],
          'charts-vendor': ['recharts'],
        },
      },
    },
  },
});
