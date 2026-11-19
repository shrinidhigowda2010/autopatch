/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#F5F0E6",
        panel: "#FBF8F2",
        line: "#E4DCCB",
        ink: "#111111",
        mist: "#3A3A3A",
        paper: "#F5F0E6",
        // legacy aliases remapped for gradual migration
        lime: "#111111",
        coral: "#C0392B",
        amber: "#B9770E",
        good: "#1E8449",
        sky: "#3A3A3A",
        bug: "#C0392B",
        fixed: "#1E8449",
        review: "#B9770E",
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "Helvetica Neue", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        "2xl": "1rem",
      },
      boxShadow: {
        card: "0 1px 2px rgba(17,17,17,0.04), 0 8px 24px rgba(17,17,17,0.06), 0 20px 40px rgba(17,17,17,0.04)",
        lift: "0 12px 32px rgba(17,17,17,0.12), 0 2px 6px rgba(17,17,17,0.06)",
        emboss: "inset 0 1px 0 rgba(255,255,255,0.65), 0 1px 2px rgba(17,17,17,0.08)",
        pressed: "inset 0 2px 6px rgba(17,17,17,0.18)",
      },
    },
  },
  plugins: [],
};
