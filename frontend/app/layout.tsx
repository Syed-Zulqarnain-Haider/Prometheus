import type { Metadata, Viewport } from "next";

import { Providers } from "@/app/providers";
import { ServiceWorkerRegister } from "@/components/pwa/service-worker-register";
import "./globals.css";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

export const metadata: Metadata = {
  title: "Prometheus",
  description: "Performance analytics dashboard",
};

/* Without this a phone assumes a ~980px desktop viewport and scales the whole page down,
 * so every responsive breakpoint in the app measures the wrong width and never fires.
 * This is what makes the mobile layout actually be a mobile layout.
 *
 * userScalable stays ON: pinch-zoom is an accessibility feature, and locking it away to
 * make an app feel "native" is not a trade worth making on a dashboard full of figures. */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Paint under the notch; the safe-area insets in the shell keep content clear of it.
  viewportFit: "cover",
  themeColor: "#0b0b0d",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <Providers>{children}</Providers>
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
