/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        night: {
          950: "#07060d",
          900: "#0d0b14",
          850: "#12101c",
        },
        ui: {
          page: "#F8F9FD",
          surface: "#ffffff",
          border: "rgba(148, 163, 184, 0.35)",
          muted: "#64748b",
          ink: "#0f172a",
          violet: "#7c3aed",
          sky: "#0ea5e9",
        },
        coral: {
          400: "#fb7185",
          500: "#f43f5e",
        },
        honey: "#fbbf24",
      },
      backgroundImage: {
        "grid-fade":
          "linear-gradient(to right, rgba(148,163,184,0.06) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.06) 1px, transparent 1px)",
        "gradient-accent": "linear-gradient(135deg, #7c3aed 0%, #2563eb 55%, #0ea5e9 100%)",
      },
      boxShadow: {
        ui: "0 10px 40px rgba(15, 23, 42, 0.06)",
        "ui-lg": "0 24px 60px rgba(124, 58, 237, 0.12)",
        card: "0 8px 30px rgba(0, 0, 0, 0.05)",
      },
      animation: {
        float: "float 18s ease-in-out infinite",
        float2: "float2 22s ease-in-out infinite",
        pulseSoft: "pulseSoft 4s ease-in-out infinite",
        shimmer: "shimmer 2.5s linear infinite",
        "spin-slow": "spinSlow 28s linear infinite",
        "data-stream": "dataStream 4s ease-in-out infinite",
        glow: "glowPulse 3s ease-in-out infinite",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "33%": { transform: "translate(30px, -20px) scale(1.05)" },
          "66%": { transform: "translate(-20px, 15px) scale(0.95)" },
        },
        float2: {
          "0%, 100%": { transform: "translate(0, 0)" },
          "50%": { transform: "translate(-40px, 30px)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "0.75" },
        },
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        spinSlow: {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        dataStream: {
          "0%, 100%": { opacity: "0.3", transform: "scaleX(0.3)" },
          "50%": { opacity: "1", transform: "scaleX(1)" },
        },
        glowPulse: {
          "0%, 100%": { boxShadow: "0 0 20px rgba(124,58,237,0.2)" },
          "50%": { boxShadow: "0 0 36px rgba(14,165,233,0.25)" },
        },
      },
    },
  },
  plugins: [],
};
