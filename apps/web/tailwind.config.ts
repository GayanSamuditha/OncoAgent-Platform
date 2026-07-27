import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#102a43",
        mist: "#f3f7fa",
        teal: "#0f766e",
      },
    },
  },
  plugins: [],
};

export default config;
