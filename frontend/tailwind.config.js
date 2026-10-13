/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#F7F8FA",
        surface: "#FFFFFF",
        primary: {
          DEFAULT: "#2563EB",
          hover: "#1D4ED8",
          subtle: "#EFF6FF",
        },
        border: {
          DEFAULT: "#E5E7EB",
          strong: "#D1D5DB",
        },
        foreground: {
          DEFAULT: "#111827",
          muted: "#4B5563",
          subtle: "#9CA3AF",
        },
        status: {
          ready: {
            bg: "#ECFDF5",
            text: "#059669",
            border: "#A7F3D0",
          },
          processing: {
            bg: "#EFF6FF",
            text: "#2563EB",
            border: "#BFDBFE",
          },
          pending: {
            bg: "#FFFBEB",
            text: "#D97706",
            border: "#FDE68A",
          },
          failed: {
            bg: "#FEF2F2",
            text: "#DC2626",
            border: "#FECACA",
          },
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
