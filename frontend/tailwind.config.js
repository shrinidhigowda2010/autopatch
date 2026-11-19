/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#101410",
        panel: "#171d18",
        line: "#2c382f",
        mist: "#9aab9d",
        paper: "#e8f0e6",
        lime: "#dff25a",
        coral: "#ff6a4a",
        amber: "#f0b429",
        sky: "#8eb6ff",
        good: "#3dce8a",
      },
      fontFamily: {
        sans: ["Outfit", "Segoe UI", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
