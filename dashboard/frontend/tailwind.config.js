/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        profit: '#22c55e',
        loss: '#ef4444',
        bg: {
          primary: '#0f172a',
          secondary: '#1e293b',
          card: '#1e293b',
        },
      },
    },
  },
  plugins: [],
}
