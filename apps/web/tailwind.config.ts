import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#11110f",
        panel: "#191916",
        line: "#34342e",
        paper: "#f4efe4",
        amber: "#e7b75f",
        mint: "#72d6a0",
        coral: "#ed6a5a",
        teal: "#4db7ad"
      }
    }
  },
  plugins: []
};

export default config;
