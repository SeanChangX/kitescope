/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#ff0050", dark: "#e60045" },
        ks: {
          primary: "#ff0050",
          "primary-dark": "#e60045",
          "primary-light": "#ff3377",
          accent: "#ff6600",
          success: "#00ff88",
          warning: "#ffaa00",
          danger: "#ff3366",
          info: "#0d9488",
        },
        bg: {
          primary: "#0a0a0a",
          secondary: "#1a1a1a",
          tertiary: "#262626",
          card: "#1a1a1a",
          input: "#262626",
        },
        text: {
          primary: "#fafafa",
          secondary: "#a3a3a3",
          muted: "#737373",
        },
        border: {
          DEFAULT: "#404040",
          light: "#525252",
          dark: "#262626",
        },
      },
      fontFamily: {
        gaming: ["Orbitron", "Noto Sans TC", "sans-serif"],
        body: ["Rajdhani", "Noto Sans TC", "sans-serif"],
        lang: ["Noto Sans TC", "sans-serif"],
      },
      ringColor: {
        DEFAULT: "#ff0050",
      },
    },
  },
  plugins: [],
};
