import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base:     "#0f1117",
        surface:  "#1a1d27",
        elevated: "#252836",
        border:   "#2e3149",
        muted:    "#7b7f9e",
        primary:  "#e8eaf0",
        accent:   "#6c63ff",
        "accent-hover": "#574fd6",
      },
      animation: {
        "pulse-ring": "pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  safelist: [
    "border-[#6c63ff]", "border-[#22c55e]", "border-[#ef4444]", "border-[#2e3149]",
    "bg-[#1e1b4b]", "bg-[#052e16]", "bg-[#2d0a0a]", "bg-[#1a1d27]",
    "text-[#6c63ff]", "text-[#3b82f6]", "text-[#f59e0b]", "text-[#22c55e]",
    "text-[#ec4899]", "text-[#06b6d4]", "text-[#f97316]",
  ],
  plugins: [],
};

export default config;
