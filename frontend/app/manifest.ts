import type { MetadataRoute } from "next";

/* The install manifest - this is what makes Prometheus installable to a phone's home
 * screen and lets it open without browser chrome.
 *
 * Next serves this at /manifest.webmanifest and injects the <link rel="manifest">
 * itself, so nothing else has to reference it. iOS ignores manifests entirely and reads
 * its own <meta>/<link> tags instead; those live in app/layout.tsx.
 *
 * `display: standalone` is the point of the exercise: launched from the home screen the
 * app gets the whole screen with no URL bar, which is what makes it feel like an app
 * rather than a bookmark. `id` is fixed so a future change of start_url does not make
 * browsers treat it as a different app and offer a second install. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Prometheus Performance",
    short_name: "Prometheus",
    description: "Mobile-app performance analytics for Terafort.",
    start_url: "/overview",
    scope: "/",
    display: "standalone",
    orientation: "portrait-primary",
    // Matches the app shell's dark surface so the status bar and splash screen do not
    // flash white before the first paint.
    background_color: "#0b0b0d",
    theme_color: "#0b0b0d",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      // Android crops icons to the launcher's shape; the maskable variant keeps the
      // flame inside the safe zone so its tip is not sliced off.
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
    shortcuts: [
      { name: "Executive Overview", url: "/overview" },
      { name: "Revenue", url: "/revenue" },
      { name: "Apps Explorer", url: "/apps" },
    ],
  };
}
