/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./public/index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#c8102e',
          light: '#e31c3d',
          dark: '#91081f',
        },
      },
    },
  },
  plugins: [],
}
