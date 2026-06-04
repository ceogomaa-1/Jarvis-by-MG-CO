/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ['class'],
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        jarvis: {
          bg: '#0a0a0a',
          surface: '#1a1a1a',
          border: 'rgba(243, 234, 217, 0.12)',
          text: '#f3ead9',
          muted: 'rgba(243, 234, 217, 0.55)',
          accent: '#c84b31',
          'accent-glow': 'rgba(200, 75, 49, 0.15)',
        },
        border: 'rgba(243, 234, 217, 0.12)',
        input: 'rgba(243, 234, 217, 0.04)',
        ring: '#c84b31',
        background: '#0a0a0a',
        foreground: '#f3ead9',
        primary: {
          DEFAULT: '#c84b31',
          foreground: '#ffffff',
        },
        secondary: {
          DEFAULT: '#1a1a1a',
          foreground: '#f3ead9',
        },
        muted: {
          DEFAULT: 'rgba(243, 234, 217, 0.06)',
          foreground: 'rgba(243, 234, 217, 0.55)',
        },
        accent: {
          DEFAULT: '#c84b31',
          foreground: '#ffffff',
        },
        destructive: {
          DEFAULT: '#ef4444',
          foreground: '#ffffff',
        },
        card: {
          DEFAULT: '#0a0a0a',
          foreground: '#f3ead9',
        },
        popover: {
          DEFAULT: '#1a1a1a',
          foreground: '#f3ead9',
        },
      },
      borderRadius: {
        lg: '12px',
        md: '8px',
        sm: '6px',
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        serif: ['var(--font-serif)', 'Georgia', 'serif'],
        mono: ['ui-monospace', '"SF Mono"', 'Menlo', 'monospace'],
        arcade: ['var(--font-arcade)', 'monospace'],
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'fade-out': {
          from: { opacity: '1' },
          to: { opacity: '0' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'fade-in': 'fade-in 200ms ease-out',
        'fade-out': 'fade-out 200ms ease-out',
        fadeIn: 'fadeIn 0.3s ease-out forwards',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
