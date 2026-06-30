/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx}", "./public/index.html"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Manrope"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      colors: {
        klein: "#3b82f6",
        profit: "#34d399",
        loss: "#fb7185",
        warn: "#fbbf24",
        zinc950: "#09090B",
      },
    },
  },
  plugins: [],
};
