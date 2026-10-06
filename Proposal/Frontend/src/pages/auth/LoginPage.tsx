import * as React from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { AlertCircle, Eye, EyeOff, Truck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Spinner } from '@/components/ui/spinner';
import { useAuth } from '@/app/auth';
import { useDocumentTitle } from '@/lib/useDocumentTitle';

export function LoginPage() {
  useDocumentTitle('Sign in');
  const { user, login, error, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/dashboard';

  // Pre-filled with the seeded System Administrator dev credentials for quick
  // local sign-in / browser verification (synthetic data — dev only).
  const [email, setEmail] = React.useState('sysadmin@ccfp.gov');
  const [password, setPassword] = React.useState('Second@123');
  const [showPassword, setShowPassword] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);

  if (user) return <Navigate to={from} replace />;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !password) return;
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch {
      // surfaced via auth.error
    } finally {
      setSubmitting(false);
    }
  }

  const busy = submitting || loading;

  return (
    <div className="flex min-h-screen w-full flex-col bg-neutral-base-50">
      <div className="flex w-full flex-1 items-center justify-center p-0 md:p-6 lg:p-10">
      <div className="grid w-full max-w-5xl grid-cols-1 overflow-hidden rounded-none border border-neutral-base-200 bg-background shadow-xl md:min-h-[560px] md:grid-cols-2 md:rounded-xl">
        {/* ------------------------------------------------------------- */}
        {/* Left — brand / value-prop card                                 */}
        {/* ------------------------------------------------------------- */}
        <aside
          aria-label="Crash Causal Factors Program overview"
          className="relative hidden flex-col justify-between gap-8 overflow-hidden bg-dot-navy p-8 text-white md:flex"
        >
          {/* Decorative background accents — purely visual. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 opacity-[0.15]"
            style={{
              backgroundImage:
                'radial-gradient(circle at 20% 10%, #205493 0, transparent 45%), radial-gradient(circle at 80% 80%, #2A496F 0, transparent 50%)',
            }}
          />
          <div className="relative z-10 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-white/10 ring-1 ring-white/20">
              <Truck className="h-5 w-5 text-alert-amber" />
            </div>
            <span className="text-xl font-bold tracking-tight">
              CC<span className="text-white">FP</span>
            </span>
          </div>

          <div className="relative z-10 flex flex-col gap-6">
            <h2 className="text-xl font-semibold leading-tight tracking-tight">
              Crash Causal Factors Program
            </h2>
            <p className="max-w-sm text-sm leading-relaxed text-white/80">
              Phase 1 — Heavy-Duty Truck Study. Collect, integrate, quality-check, analyze, and
              share data on fatal crashes involving Class 7/8 commercial motor vehicles.
            </p>

            <ul className="mt-2 flex flex-col gap-3 text-sm text-white/90">
              <li className="flex items-start gap-3">
                <CheckIcon />
                <span>End-to-end crash lifecycle from initial incident through publication</span>
              </li>
              <li className="flex items-start gap-3">
                <CheckIcon />
                <span>Source data mapping, quality control, and completeness tracking</span>
              </li>
              <li className="flex items-start gap-3">
                <CheckIcon />
                <span>Causal-factor analysis with role- and scope-based access control</span>
              </li>
              <li className="flex items-start gap-3">
                <CheckIcon />
                <span>De-identified public outputs with full data provenance and audit</span>
              </li>
            </ul>
          </div>

          <div className="relative z-10 flex flex-col gap-2 border-t border-white/10 pt-5 text-xs leading-snug text-white/60">
            <span>FMCSA · U.S. Department of Transportation</span>
            <div className="flex items-center justify-between">
              <span>Development environment · 100% synthetic data · No real PII</span>
              <span className="uppercase tracking-wider">v1.0</span>
            </div>
          </div>
        </aside>

        {/* ------------------------------------------------------------- */}
        {/* Right — auth form card                                         */}
        {/* ------------------------------------------------------------- */}
        <section
          aria-label="Sign in"
          className="flex flex-col justify-center bg-background p-6 sm:p-8 lg:p-10"
        >
          <div className="mx-auto flex w-full max-w-md flex-col gap-8">
            <div className="space-y-1.5">
              <h1 className="text-display-sm font-semibold">Sign in</h1>
              <p className="text-sm text-muted-foreground">
                Access the CCFP IT Solution with your assigned credentials.
              </p>
            </div>

            {error ? (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Sign-in failed</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : null}

            <form onSubmit={onSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  placeholder="name@agency.gov"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="pr-10 [&::-ms-reveal]:hidden [&::-ms-clear]:hidden"
                  />
                  <button
                    type="button"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword((s) => !s)}
                    className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-muted-foreground transition-colors hover:text-foreground focus:outline-none"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" aria-hidden="true" />
                    ) : (
                      <Eye className="h-4 w-4" aria-hidden="true" />
                    )}
                  </button>
                </div>
              </div>
              <Button type="submit" disabled={busy || !email || !password} className="w-full">
                {busy ? <Spinner className="h-4 w-4" /> : null}
                {busy ? 'Signing in…' : 'Sign in'}
              </Button>
            </form>

            <p className="text-center text-xs leading-snug text-muted-foreground">
              FMCSA · Crash Causal Factors Program · Heavy-Duty Truck Study
            </p>
          </div>
        </section>
      </div>
      </div>
    </div>
  );
}

function CheckIcon(): JSX.Element {
  return (
    <span
      aria-hidden="true"
      className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-alert-amber/20 text-alert-amber ring-1 ring-alert-amber/30"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 20 20"
        fill="currentColor"
        className="h-3 w-3"
      >
        <path
          fillRule="evenodd"
          d="M16.704 5.29a1 1 0 010 1.42l-7.5 7.5a1 1 0 01-1.42 0l-3.5-3.5a1 1 0 011.42-1.42L8.5 12.08l6.79-6.79a1 1 0 011.414 0z"
          clipRule="evenodd"
        />
      </svg>
    </span>
  );
}
