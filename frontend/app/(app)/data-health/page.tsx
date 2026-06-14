import { DataHealthClient } from "@/components/admin/data-health-client";
import { PageHeader } from "@/components/layout/page-header";

export default function DataHealthPage() {
  return (
    <div>
      <PageHeader
        title="Data Health"
        description="Sync freshness, run history, integrity status, and unmapped apps."
      />
      <DataHealthClient />
    </div>
  );
}
