import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: "#0a0e14",
          panel: "#10151f",
          border: "#1c2433",
          muted: "#8b98ad",
          text: "#dbe2ef",
          accent: "#38bdf8",
          green: "#34d399",
          red: "#f87171",
          amber: "#fbbf24",
          violet: "#a78bfa",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
