/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Dark navy base palette
        surface: {
          DEFAULT: '#0a0f1e',
          50:  '#f0f4ff',
          100: '#e0e8ff',
          900: '#0a0f1e',
          800: '#0f1629',
          700: '#141d35',
          600: '#1a2540',
          500: '#1f2d4d',
        },
        card: '#111827',
        border: '#1f2937',
        'border-subtle': '#374151',
        // Accent colours
        primary: {
          DEFAULT: '#3b82f6',
          50:  '#eff6ff',
          100: '#dbeafe',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
        success: {
          DEFAULT: '#10b981',
          50:  '#ecfdf5',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
        },
        warning: {
          DEFAULT: '#f59e0b',
          50:  '#fffbeb',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
        },
        danger: {
          DEFAULT: '#ef4444',
          400: '#f87171',
          500: '#ef4444',
          600: '#dc2626',
        },
        muted: '#6b7280',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 2s linear infinite',
        'slide-in': 'slideIn 0.2s ease-out',
        'fade-in': 'fadeIn 0.3s ease-out',
      },
      keyframes: {
        slideIn: {
          '0%': { transform: 'translateY(-8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
