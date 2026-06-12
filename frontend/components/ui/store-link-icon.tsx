"use client";

import { ExternalLink } from "lucide-react";

import { primaryStoreUrl } from "@/lib/store-links";

/** Small icon that opens the app's store page in a new tab. Click does NOT bubble
 *  (so a surrounding row's navigation isn't triggered). Renders nothing if no ID. */
export function StoreLinkIcon({
  androidPackage,
  appleId,
}: {
  androidPackage: string | null | undefined;
  appleId: number | string | null | undefined;
}) {
  const url = primaryStoreUrl(androidPackage, appleId);
  if (!url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title="Open store page"
      onClick={(e) => e.stopPropagation()}
      className="inline-flex text-muted-foreground hover:text-foreground"
    >
      <ExternalLink className="h-3.5 w-3.5" />
    </a>
  );
}
