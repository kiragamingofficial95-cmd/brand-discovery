import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0b1220",
        card: "#111a2e",
        accent: "#38bdf8",
        muted: "#94a3b8",
      },
    },
  },
  plugins: [],
};
export default config;