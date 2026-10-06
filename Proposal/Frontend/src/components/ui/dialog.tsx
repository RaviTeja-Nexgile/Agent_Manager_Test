import * as React from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DialogContextValue {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}
const DialogCtx = React.createContext<DialogContextValue | null>(null);

export interface DialogProps {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (v: boolean) => void;
  children?: React.ReactNode;
}

export function Dialog({ open: controlled, defaultOpen, onOpenChange, children }: DialogProps) {
  const [internal, setInternal] = React.useState(defaultOpen ?? false);
  const open = controlled ?? internal;
  const handleChange = React.useCallback(
    (v: boolean) => {
      if (controlled === undefined) setInternal(v);
      onOpenChange?.(v);
    },
    [controlled, onOpenChange],
  );
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleChange(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, handleChange]);

  // Lock background scroll while the dialog is open. The portal mounts the
  // dialog under <body>, but the AppShell uses an inner <main> as its scroll
  // container — pin both so the page can't scroll behind the modal.
  React.useEffect(() => {
    if (!open) return;
    const html = document.documentElement;
    const body = document.body;
    const main = document.querySelector('main');
    const previous = {
      htmlOverflow: html.style.overflow,
      bodyOverflow: body.style.overflow,
      mainOverflow: main?.style.overflow ?? '',
    };
    html.style.overflow = 'hidden';
    body.style.overflow = 'hidden';
    if (main) main.style.overflow = 'hidden';
    return () => {
      html.style.overflow = previous.htmlOverflow;
      body.style.overflow = previous.bodyOverflow;
      if (main) main.style.overflow = previous.mainOverflow;
    };
  }, [open]);

  return (
    <DialogCtx.Provider value={{ open, onOpenChange: handleChange }}>{children}</DialogCtx.Provider>
  );
}

interface DialogTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
}
export const DialogTrigger = React.forwardRef<HTMLButtonElement, DialogTriggerProps>(
  ({ onClick, ...props }, ref) => {
    const ctx = React.useContext(DialogCtx);
    return (
      <button
        ref={ref}
        type="button"
        onClick={(e) => {
          ctx?.onOpenChange(true);
          onClick?.(e);
        }}
        {...props}
      />
    );
  },
);
DialogTrigger.displayName = 'DialogTrigger';

export const DialogContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => {
    const ctx = React.useContext(DialogCtx);
    if (!ctx?.open) return null;
    if (typeof document === 'undefined') return null;
    return createPortal(
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="absolute inset-0 bg-black/55 animate-fade-in"
          onClick={() => ctx.onOpenChange(false)}
          aria-hidden
        />
        <div
          ref={ref}
          role="dialog"
          aria-modal="true"
          className={cn(
            'relative z-10 flex w-full max-w-lg max-h-[90vh] flex-col overflow-hidden rounded-lg border bg-background p-6 shadow-modal animate-slide-up',
            className,
          )}
          {...props}
        >
          {children}
          <button
            type="button"
            aria-label="Close"
            onClick={() => ctx.onOpenChange(false)}
            className="absolute right-3 top-3 inline-flex h-7 w-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>,
      document.body,
    );
  },
);
DialogContent.displayName = 'DialogContent';

export function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        '-mx-6 mb-4 flex shrink-0 flex-col gap-1.5 border-b border-border px-6 pb-4 text-left',
        className,
      )}
      {...props}
    />
  );
}

export function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        '-mx-6 mt-4 flex shrink-0 flex-col-reverse border-t border-border px-6 pt-4 sm:flex-row sm:justify-end sm:gap-2',
        className,
      )}
      {...props}
    />
  );
}

export function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn('text-lg font-semibold leading-none tracking-tight', className)}
      {...props}
    />
  );
}

export function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('text-sm text-muted-foreground', className)} {...props} />;
}
