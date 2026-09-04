/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        cyber: {
          bg: '#0B0F17',
          card: '#131B2B',
          border: '#1E293B',
          primary: '#00F0FF',
          accent: '#7928CA',
          success: '#10B981',
          warning: '#F59E0B',
          danger: '#EF4444',
          muted: '#94A3B8',
        }
      },
      fontFamily: {
        sans: ['Kanit', 'Inter', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
