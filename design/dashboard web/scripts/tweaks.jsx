/* ============================================================================
   TWEAKS — optional in-design controls.
   Mounts a small React root that ONLY renders the Tweaks panel. The dashboard
   itself is plain HTML/CSS; tweaks rewrite design tokens on :root.

   IMPORTANT: the DEFAULT for accent & corners is "Theme", which CLEARS any
   inline override so the Swiss Ledger tokens (which differ per light/dark mode)
   flow through untouched. Only an explicit alternate choice overrides them —
   so theme-switching always works and the base look is never clobbered.
   ============================================================================ */
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "Theme",
  "density": "Comfortable"
}/*EDITMODE-END*/;

/* Editorial opt-in accents (single value; deliberately chosen by the user).
   "Theme" is special: it removes the override and defers to tokens.css. */
const ACCENTS = {
  Forest: { accent: "#3f7d5e", strong: "#336848", soft: "rgba(63,125,94,0.14)",  bar: "#3f7d5e", gradTo: "#7d5a8c" },
  Plum:   { accent: "#7d5a8c", strong: "#6a4a78", soft: "rgba(125,90,140,0.16)", bar: "#7d5a8c", gradTo: "#b5872f" },
  Gold:   { accent: "#b5872f", strong: "#9a6f1f", soft: "rgba(181,135,47,0.16)", bar: "#b5872f", gradTo: "#7d5a8c" },
};

const ACCENT_PROPS = ["--color-accent", "--color-accent-strong", "--color-accent-soft",
                      "--color-brand", "--chart-bar", "--chart-grad-from", "--chart-grad-to"];

function applyTweaks(t) {
  const root = document.documentElement.style;

  // ---- accent ----
  if (t.accent === "Theme" || !ACCENTS[t.accent]) {
    // clear overrides → let the per-mode Swiss Ledger tokens show
    ACCENT_PROPS.forEach((p) => root.removeProperty(p));
  } else {
    const a = ACCENTS[t.accent];
    root.setProperty("--color-accent", a.accent);
    root.setProperty("--color-accent-strong", a.strong);
    root.setProperty("--color-accent-soft", a.soft);
    root.setProperty("--color-brand", a.accent);
    root.setProperty("--chart-bar", a.bar);
    root.setProperty("--chart-grad-from", a.accent);
    root.setProperty("--chart-grad-to", a.gradTo);
  }

  // ---- density (never conflicts with theme colors) ----
  if (t.density === "Compact") {
    root.setProperty("--card-pad", "14px");
    root.setProperty("--grid-gap", "10px");
  } else {
    root.removeProperty("--card-pad");
    root.removeProperty("--grid-gap");
  }

  if (window.__rerenderCharts) window.__rerenderCharts();
}

function TweaksApp() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  React.useEffect(() => { applyTweaks(t); }, [t]);
  return (
    React.createElement(TweaksPanel, { title: "Tweaks" },
      React.createElement(TweakSection, { label: "Accent" }),
      React.createElement(TweakRadio, { label: "Color", value: t.accent,
        options: ["Theme", "Forest", "Plum", "Gold"], onChange: (v) => setTweak("accent", v) }),
      React.createElement(TweakSection, { label: "Density" }),
      React.createElement(TweakRadio, { label: "Spacing", value: t.density,
        options: ["Comfortable", "Compact"], onChange: (v) => setTweak("density", v) })
    )
  );
}

ReactDOM.createRoot(document.getElementById("tweaks-root")).render(React.createElement(TweaksApp));
