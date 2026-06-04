import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Branding Telediagnosis (z panelu desktopowego)
        brand: {
          bg: "#0a2d37",
          surface: "#0e3b49",
          border: "#214652",
          accent: "#1dab5a",
          accentHover: "#168a48",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
