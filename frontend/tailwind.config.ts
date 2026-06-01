import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--app-bg)",
        surface: "var(--app-surface)",
        border: "var(--app-border)",
        ink: {
          DEFAULT: "var(--app-fg)",
          muted: "var(--app-muted)",
          dim: "var(--app-dim)",
        },
        accent: {
          violet: "#a78bfa",
          cyan: "#22d3ee",
          emerald: "#34d399",
          amber: "#fbbf24",
          rose: "#fb7185",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "PingFang SC",
          "Noto Sans SC",
          "Microsoft YaHei",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "display-sm": ["3rem", { lineHeight: "1.05", letterSpacing: "-0.025em" }],
        display: ["4rem", { lineHeight: "1.02", letterSpacing: "-0.028em" }],
        "display-lg": ["5.25rem", { lineHeight: "0.98", letterSpacing: "-0.03em" }],
        "display-xl": ["6.5rem", { lineHeight: "0.96", letterSpacing: "-0.032em" }],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(167,139,250,0.25), 0 8px 40px -10px rgba(167,139,250,0.35)",
        "glow-cyan":
          "0 0 0 1px rgba(34,211,238,0.25), 0 8px 40px -10px rgba(34,211,238,0.35)",
        "glow-soft":
          "0 16px 60px -20px rgba(124, 58, 237, 0.4), 0 0 0 1px rgba(167, 139, 250, 0.18)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "grid-fade":
          "linear-gradient(to bottom, transparent, rgba(10,10,15,1) 80%)",
        "brand-gradient":
          "linear-gradient(120deg, #7c3aed 0%, #0891b2 55%, #06b6d4 100%)",
        "warm-gradient":
          "linear-gradient(120deg, #fb7185 0%, #fbbf24 50%, #f472b6 100%)",
      },
      keyframes: {
        aurora: {
          "0%, 100%": { transform: "translate3d(-10%, -5%, 0) scale(1)" },
          "50%": { transform: "translate3d(10%, 5%, 0) scale(1.1)" },
        },
        "aurora-drift": {
          "0%, 100%": { transform: "translate3d(15%, 8%, 0) scale(1.05)" },
          "50%": { transform: "translate3d(-12%, -8%, 0) scale(0.95)" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.2" },
        },
        "float-soft": {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        aurora: "aurora 18s ease-in-out infinite",
        "aurora-slow": "aurora 28s ease-in-out infinite",
        "aurora-drift": "aurora-drift 24s ease-in-out infinite",
        blink: "blink 1.1s ease-in-out infinite",
        "float-soft": "float-soft 5s ease-in-out infinite",
        "fade-up": "fade-up 0.55s cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
