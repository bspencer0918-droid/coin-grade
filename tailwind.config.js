/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,js}'],
  theme: {
    extend: {
      colors: {
        gold: {
          50:  '#fdf8ec',
          100: '#faefd0',
          200: '#f5dba1',
          300: '#eec163',
          400: '#e8a63c',
          500: '#df8c22',
          600: '#c56d18',
          700: '#a35117',
          800: '#85411a',
          900: '#6d3619',
          950: '#3e1b09',
        },
        parchment: {
          50:  '#faf6ef',
          100: '#f2e9d8',
          200: '#e5d0b0',
          300: '#d4b07f',
          400: '#c59257',
          500: '#b87b3d',
          600: '#9d6432',
          700: '#7f4e2b',
          800: '#684229',
          900: '#573726',
          950: '#2f1b12',
        },
      },
      fontFamily: {
        serif:  ['Georgia', '"Times New Roman"', 'serif'],
        display: ['"Palatino Linotype"', 'Palatino', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
}
