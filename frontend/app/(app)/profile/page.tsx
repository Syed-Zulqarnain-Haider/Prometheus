import type { Metadata } from "next";

import { PageHeader } from "@/components/layout/page-header";
import { ProfileClient } from "@/components/profile/profile-client";

export const metadata: Metadata = { title: "My profile - Prometheus" };

export default function ProfilePage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="My profile"
        description="Your picture, name and details - and when this account was last active."
      />
      <ProfileClient />
    </div>
  );
}
