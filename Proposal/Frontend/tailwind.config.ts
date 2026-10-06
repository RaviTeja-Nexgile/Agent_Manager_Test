import type { Config } from 'tailwindcss';
import forms from '@tailwindcss/forms';
import animate from 'tailwindcss-animate';

/**
 * CCFP — Crash Causal Factors Program (FMCSA) Tailwind theme.
 *
 * Federal/gov SaaS palette aligned to USWDS / DOT branding.
 * - dot-navy: top bar / brand
 * - federal-blue: accent
 * - alert-amber / alert-red: reserved for warnings + errors
 * - shadcn/ui semantic tokens (CSS variables) live alongside.
 */
const config: Config = {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: { center: true, padding: '2rem', screens: { '2xl': '1400px' } },
    extend: {
      colors: {
        'dot-navy': {
          DEFAULT: '#0F2A4A',
          50: '#ECF1F8',
          100: '#CFD9E8',
          200: '#9BAEC9',
          300: '#6783A8',
          400: '#335E89',
          500: '#0F2A4A',
          600: '#0C2440',
          700: '#091C33',
          800: '#061427',
          900: '#040D1A',
        },
        'federal-blue': {
          DEFAULT: '#1F5AA8',
          50: '#ECF2FB',
          100: '#CFDDF2',
          200: '#9BBAE3',
          300: '#6796D2',
          400: '#3372BE',
          500: '#1F5AA8',
          600: '#194A8D',
          700: '#143B71',
          800: '#0E2C56',
          900: '#091D3A',
        },
        'neutral-base': {
          DEFAULT: '#4B5563',
          50: '#F8FAFC',
          100: '#F4F6FA',
          200: '#E2E8F0',
          300: '#CBD5E1',
          400: '#94A3B8',
          500: '#4B5563',
          600: '#374151',
          700: '#1F2937',
          800: '#111827',
          900: '#0B1220',
        },
        'alert-amber': {
          DEFAULT: '#B45309',
          light: '#FEF3C7',
          50: '#FFFBEB',
          100: '#FEF3C7',
          200: '#FDE68A',
          300: '#FCD34D',
          400: '#F59E0B',
          500: '#B45309',
          600: '#92400E',
          700: '#78350F',
        },
        'alert-red': {
          DEFAULT: '#B91C1C',
          light: '#FEE2E2',
          50: '#FEF2F2',
          100: '#FEE2E2',
          200: '#FECACA',
          300: '#FCA5A5',
          400: '#EF4444',
          500: '#B91C1C',
          600: '#991B1B',
          700: '#7F1D1D',
        },
        'success-green': {
          DEFAULT: '#15803D',
          50: '#F0FDF4',
          100: '#DCFCE7',
          200: '#BBF7D0',
          300: '#86EFAC',
          400: '#4ADE80',
          500: '#15803D',
          600: '#166534',
          700: '#14532D',
        },
        'federal-gold': {
          DEFAULT: '#B45309',
          50: '#FFFBEB',
          100: '#FEF3C7',
          200: '#FDE68A',
          300: '#FCD34D',
          400: '#D97706',
          500: '#B45309',
          600: '#92400E',
          700: '#78350F',
        },
        success: { DEFAULT: '#15803D', light: '#DCFCE7', foreground: '#FFFFFF' },
        info: { DEFAULT: '#1F5AA8', light: '#CFDDF2', foreground: '#FFFFFF' },
        warning: { DEFAULT: '#B45309', light: '#FEF3C7', foreground: '#111111' },
        error: { DEFAULT: '#B91C1C', light: '#FEE2E2', foreground: '#FFFFFF' },

        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        brand: 'hsl(var(--brand))',
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
        popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
      },
      fontFamily: {
        sans: ['"Public Sans"', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
        eyebrow: ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.08em' }],
        'display-sm': ['1.5rem', { lineHeight: '2rem', letterSpacing: '-0.005em', fontWeight: '600' }],
        display: ['1.875rem', { lineHeight: '2.25rem', letterSpacing: '-0.01em', fontWeight: '600' }],
        'display-lg': ['2.25rem', { lineHeight: '2.625rem', letterSpacing: '-0.015em', fontWeight: '600' }],
      },
      letterSpacing: { eyebrow: '0.08em' },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      boxShadow: {
        xs: '0 1px 2px 0 rgb(15 42 74 / 0.04)',
        card: '0 1px 2px 0 rgb(15 42 74 / 0.04), 0 1px 3px 0 rgb(15 42 74 / 0.06)',
        pop: '0 4px 12px -2px rgb(15 42 74 / 0.08), 0 2px 4px -2px rgb(15 42 74 / 0.06)',
        modal: '0 16px 40px -8px rgb(15 42 74 / 0.18), 0 6px 12px -4px rgb(15 42 74 / 0.10)',
        'focus-ring': '0 0 0 3px hsl(var(--ring) / 0.35)',
      },
      keyframes: {
        'fade-in': { from: { opacity: '0' }, to: { opacity: '1' } },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.2s ease-out',
        'slide-up': 'slide-up 0.24s cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [forms, animate],
};

export default config;
