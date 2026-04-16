import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "#0D0D0D",
          secondary: "#1A1A2E",
          tertiary: "#16213E",
        },
        accent: {
          primary: "#7C3AED",
          secondary: "#F59E0B",
          success: "#10B981",
          warning: "#EAB308",
          danger: "#EF4444",
        },
        border: {
          DEFAULT: "#2D2D44",
        },
      },
    },
  },
  plugins: [],
};

export default config;
