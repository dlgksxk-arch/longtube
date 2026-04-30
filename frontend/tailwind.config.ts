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
          // v2.3.0: #2D2D44 는 bg-primary(#0D0D0D) 대비 1.41:1 로
          //         WCAG 2.1 AA non-text 3:1 기준에 미달이었다.
          //         #4B5167 로 올려 3:1 이상 확보.
          DEFAULT: "#4B5167",
          subtle: "#2D2D44",
        },
      },
    },
  },
  plugins: [],
};

export default config;
