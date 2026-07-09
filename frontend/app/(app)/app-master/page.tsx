import { AppMasterClient } from "@/components/app-master/app-master-client";
import { PageHeader } from "@/components/layout/page-header";

export default function AppMasterPage() {
  return (
    <div>
      <PageHeader
        title="App Master"
        description="The cross-platform app master list (BigQuery app_master_v2). Admins can edit the curated fields; changes write back to BigQuery."
      />
      <AppMasterClient />
    </div>
  );
}
