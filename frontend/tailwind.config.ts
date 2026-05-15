import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#020617", panel: "#0F172A", border: "#334155",
        muted: "#94A3B8", text: "#F8FAFC", accent: "#22C55E",
        elev: "#1A1E2F",
      },
      fontFamily: {
        sans: ["Fira Sans", "system-ui", "sans-serif"],
        mono: ["Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
