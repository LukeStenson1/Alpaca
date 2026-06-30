/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx}", "./public/index.html"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      colors: {
        klein: "#002FA7",
        profit: "#16A34A",
        loss: "#DC2626",
        warn: "#D97706",
        zinc950: "#09090B",
      },
    },
  },
  plugins: [],
};
