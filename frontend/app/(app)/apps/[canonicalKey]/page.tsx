import { PageHeader } from "@/components/layout/page-header";

export default function AppDetailPage({
  params,
}: {
  params: { canonicalKey: string };
}) {
  return (
    <PageHeader
      title={`App: ${decodeURIComponent(params.canonicalKey)}`}
      description="Per-app detail. Charts arrive in a later step."
    />
  );
}
