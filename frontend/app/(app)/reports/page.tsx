import { ReportsClient } from "@/components/reports/reports-client";
import { PageHeader } from "@/components/layout/page-header";

export default function ReportsPage() {
  return (
    <div>
      <PageHeader
        title="Reports"
        description="Build, save, share, and export reports — always scoped to your access."
      />
      <ReportsClient />
    </div>
  );
}
