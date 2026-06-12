import type { Config } from "tailwindcss";

/* Color names map to the ported Swiss Ledger tokens (design/tokens.css).
   Shadcn-style component names are bridged to the owner's --color-* vars so
   every component renders the exact theme in both modes. */
const config: Config = {
  darkMode: ["selector", ':root:not([data-theme="light"])'],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "var(--color-border)",
        "border-strong": "var(--color-border-strong)",
        input: "var(--color-border)",
        ring: "var(--color-accent)",
        background: "var(--color-bg-app)",
        foreground: "var(--color-text-primary)",
        sidebar: "var(--color-bg-sidebar)",
        primary: {
          DEFAULT: "var(--color-accent)",
          strong: "var(--color-accent-strong)",
          foreground: "var(--color-accent-foreground)",
        },
        secondary: {
          DEFAULT: "var(--color-bg-elevated)",
          foreground: "var(--color-text-primary)",
        },
        destructive: {
          DEFAULT: "var(--color-negative)",
          foreground: "var(--color-accent-foreground)",
        },
        muted: {
          DEFAULT: "var(--color-bg-card-sunken)",
          foreground: "var(--color-text-secondary)",
        },
        accent: {
          DEFAULT: "var(--color-bg-elevated)",
          foreground: "var(--color-text-primary)",
        },
        popover: {
          DEFAULT: "var(--color-bg-card)",
          foreground: "var(--color-text-primary)",
        },
        card: {
          DEFAULT: "var(--color-bg-card)",
          sunken: "var(--color-bg-card-sunken)",
          foreground: "var(--color-text-primary)",
        },
        positive: "var(--color-positive)",
        negative: "var(--color-negative)",
      },
      fontFamily: {
        sans: "var(--font-sans)",
        display: "var(--font-display)",
      },
      borderRadius: {
        lg: "var(--radius-card)",
        md: "var(--radius-inner)",
        sm: "var(--radius-chip)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        pop: "var(--shadow-pop)",
      },
    },
  },
  plugins: [],
};
export default config;
