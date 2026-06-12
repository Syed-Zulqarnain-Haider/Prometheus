"use client";

import { ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AppDetail } from "@/lib/types";
import { appStoreUrl, playStoreUrl } from "@/lib/store-links";

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-sm">{value ?? "—"}</div>
    </div>
  );
}

export function MetadataCard({ app }: { app: AppDetail }) {
  const play = playStoreUrl(app.android_package);
  const appStore = appStoreUrl(app.apple_id);

  return (
    <Card>
      <CardHeader>
        <CardTitle>App Metadata</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Field label="Publisher" value={app.publisher} />
          <Field label="Pod" value={app.pod} />
          <Field label="Pod Owner" value={app.pod_owner} />
          <Field label="HoU" value={app.hou} />
          <Field label="Category" value={app.app_category} />
          <Field label="Ownership" value={app.ownership_type} />
          <Field label="Android package" value={app.android_package} />
          <Field label="Apple ID" value={app.apple_id ? String(app.apple_id) : null} />
          <Field label="Mapped" value={app.is_mapped == null ? null : app.is_mapped ? "Yes" : "No"} />
        </div>

        {(play || appStore) && (
          <div className="flex flex-wrap gap-2 border-t pt-3">
            {play && (
              <Button asChild variant="outline" size="sm">
                <a href={play} target="_blank" rel="noopener noreferrer">
                  View on Google Play <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </Button>
            )}
            {appStore && (
              <Button asChild variant="outline" size="sm">
                <a href={appStore} target="_blank" rel="noopener noreferrer">
                  View on App Store <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
