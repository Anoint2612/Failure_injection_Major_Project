/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#09090b',
        surface: '#18181b',
        border: '#27272a',
        primary: '#3b82f6',
        danger: '#ef4444',
        success: '#22c55e'
      }
    },
  },
  plugins: [],
}
