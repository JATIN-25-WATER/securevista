/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#0b0f17',
          800: '#111827',
          700: '#1f2937',
          600: '#374151',
          500: '#4b5563',
        },
        alert: {
          red: '#ef4444',
          amber: '#f59e0b',
          blue: '#3b82f6',
        }
      },
      animation: {
        'pulse-fast': 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'flash-red': 'flashRed 1.5s infinite',
      },
      keyframes: {
        flashRed: {
          '0%, 100%': { boxShadow: '0 0 25px rgba(239, 68, 68, 0.8), inset 0 0 15px rgba(239, 68, 68, 0.5)' },
          '50%': { boxShadow: '0 0 50px rgba(239, 68, 68, 1), inset 0 0 30px rgba(239, 68, 68, 0.8)' },
        }
      }
    },
  },
  plugins: [],
}
