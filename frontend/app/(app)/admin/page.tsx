import { AdminClient } from "@/components/admin/admin-client";
import { PageHeader } from "@/components/layout/page-header";

export default function AdminPage() {
  return (
    <div>
      <PageHeader
        title="Admin"
        description="Users, roles, revenue targets, and the audit log."
      />
      <AdminClient />
    </div>
  );
}
