import { PageHeader } from "@/components/layout/page-header";

export default function OverviewPage() {
  return (
    <div>
      <PageHeader
        title="Executive Overview"
        description="KPIs, revenue vs spend, and top apps. Charts arrive in a later step."
      />
      <p className="text-sm text-muted-foreground">
        Use the global filter bar above — its state is synced to the URL.
      </p>
    </div>
  );
}
