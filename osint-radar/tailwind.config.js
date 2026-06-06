/** @type {import('tailwindcss').Config} */

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    container: {
      center: true,
    },
    extend: {
      colors: {
        radar: {
          bg: "#0a0e1a",
          card: "#111827",
          border: "#1e293b",
          cyan: "#00f0ff",
          orange: "#ff6b35",
          green: "#10b981",
          red: "#ef4444",
          yellow: "#f59e0b",
          muted: "#64748b",
          text: "#e2e8f0",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
        sans: ["Noto Sans SC", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 20px rgba(0, 240, 255, 0.3)",
        "glow-orange": "0 0 20px rgba(255, 107, 53, 0.3)",
        "glow-sm": "0 0 10px rgba(0, 240, 255, 0.15)",
      },
      animation: {
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "scan-line": "scan-line 3s linear infinite",
        float: "float 6s ease-in-out infinite",
      },
      keyframes: {
        "pulse-glow": {
          "0%, 100%": { boxShadow: "0 0 10px rgba(0, 240, 255, 0.2)" },
          "50%": { boxShadow: "0 0 25px rgba(0, 240, 255, 0.5)" },
        },
        "scan-line": {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
      },
    },
  },
  plugins: [],
};
