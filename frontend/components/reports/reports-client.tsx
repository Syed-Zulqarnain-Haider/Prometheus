"use client";

import { Check, Download, Play, Trash2, X } from "lucide-react";
import { useState } from "react";

import { ReportBuilder } from "@/components/reports/report-builder";
import { ShareDialog } from "@/components/reports/share-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiDownload, ApiError } from "@/lib/api-client";
import {
  useDecideShare,
  useDeleteReport,
  useMe,
  usePendingShares,
  useRunReport,
  useSavedReports,
  useSharedReports,
} from "@/lib/api-hooks";
import { metricLabel } from "@/lib/report-metrics";
import type { ExportFormat, ReportRunResult, SavedReport } from "@/lib/types";

type Tab = "builder" | "mine" | "shared" | "approvals";

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return new Intl.NumberFormat("en-US").format(value);
  return String(value);
}

function ResultTable({ result }: { result: ReportRunResult }) {
  const dimensionKey = result.group_by === "date" ? "bucket" : result.group_by;
  if (result.columns.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        None of this report&apos;s metrics are visible to you.
      </p>
    );
  }
  if (result.rows.length === 0) {
    return <p className="text-xs text-muted-foreground">No rows for your access + filters.</p>;
  }
  return (
    <div className="overflow-auto rounded-md border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="px-3 py-2">{dimensionKey}</th>
            {result.columns.map((column) => (
              <th key={column} className="px-3 py-2 text-right">
                {metricLabel(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.slice(0, 50).map((row, index) => (
            <tr key={index} className="border-t">
              <td className="px-3 py-1.5">{formatCell(row[dimensionKey])}</td>
              {result.columns.map((column) => (
                <td key={column} className="px-3 py-1.5 text-right tabular-nums">
                  {formatCell(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportCard({
  report,
  canExport,
  canShare,
}: {
  report: SavedReport;
  canExport: boolean;
  canShare: boolean;
}) {
  const run = useRunReport();
  const deleteReport = useDeleteReport();
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);

  async function doExport(format: ExportFormat) {
    setExportError(null);
    setExporting(format);
    try {
      const ext = format === "xlsx" ? "xlsx" : "csv";
      await apiDownload(
        "/api/v1/export",
        { format, report_id: report.id },
        `${report.name}.${ext}`,
      );
    } catch (error) {
      setExportError(
        error instanceof ApiError ? error.message : "Export failed — please retry.",
      );
    } finally {
      setExporting(null);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
        <div>
          <CardTitle className="normal-case tracking-normal text-sm font-semibold text-foreground">
            {report.name}
          </CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Group by {report.group_by} · {report.columns.length} metric(s)
            {!report.is_owner && <span className="ml-1">· shared</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => run.mutate(report.id)}
            disabled={run.isPending}
          >
            <Play className="h-4 w-4" />
            Run
          </Button>
          {canShare && report.is_owner && <ShareDialog reportId={report.id} />}
          {canExport && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => doExport("csv")}
                disabled={exporting !== null}
              >
                <Download className="h-4 w-4" />
                CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => doExport("xlsx")}
                disabled={exporting !== null}
              >
                XLSX
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled
                title="Google Sheets export is not enabled in v1."
              >
                Sheets
              </Button>
            </>
          )}
          {report.is_owner && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => deleteReport.mutate(report.id)}
              aria-label={`Delete ${report.name}`}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardHeader>
      {(run.data || run.isError || exportError) && (
        <CardContent className="space-y-2">
          {exportError && <p className="text-xs text-destructive">{exportError}</p>}
          {run.isError && (
            <p className="text-xs text-destructive">
              {run.error instanceof Error ? run.error.message : "Run failed."}
            </p>
          )}
          {run.data && <ResultTable result={run.data} />}
        </CardContent>
      )}
    </Card>
  );
}

function ApprovalsQueue() {
  const { data: pending } = usePendingShares(true);
  const approve = useDecideShare("approve");
  const reject = useDecideShare("reject");
  const items = pending ?? [];

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No share requests awaiting approval.</p>;
  }

  return (
    <div className="space-y-2">
      {items.map((share) => (
        <Card key={share.id}>
          <CardContent className="flex items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">
                {share.report_name ?? "Report"}
              </p>
              <p className="text-xs text-muted-foreground">Pending approval</p>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                className="gap-1"
                onClick={() => approve.mutate(share.id)}
                disabled={approve.isPending}
              >
                <Check className="h-4 w-4" />
                Approve
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-1"
                onClick={() => reject.mutate(share.id)}
                disabled={reject.isPending}
              >
                <X className="h-4 w-4" />
                Reject
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function ReportsClient() {
  const { data: me } = useMe();
  const [tab, setTab] = useState<Tab>("builder");

  const { data: myReports } = useSavedReports();
  const { data: sharedReports } = useSharedReports();

  const canExport = me?.capabilities.includes("export") ?? false;
  const canShare = me?.capabilities.includes("share_report") ?? false;
  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;

  const tabs: { value: Tab; label: string }[] = [
    { value: "builder", label: "Builder" },
    { value: "mine", label: "My reports" },
    { value: "shared", label: "Shared with me" },
    ...(isAdmin ? [{ value: "approvals" as Tab, label: "Approvals" }] : []),
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 border-b">
        {tabs.map((entry) => (
          <button
            key={entry.value}
            type="button"
            onClick={() => setTab(entry.value)}
            className={`relative -mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              tab === entry.value
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {tab === "builder" && <ReportBuilder />}

      {tab === "mine" && (
        <div className="space-y-3">
          {(myReports ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No saved reports yet — build one in the Builder tab.
            </p>
          ) : (
            (myReports ?? []).map((report) => (
              <ReportCard
                key={report.id}
                report={report}
                canExport={canExport}
                canShare={canShare}
              />
            ))
          )}
        </div>
      )}

      {tab === "shared" && (
        <div className="space-y-3">
          {(sharedReports ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No reports have been shared with you.
            </p>
          ) : (
            (sharedReports ?? []).map((report) => (
              <ReportCard
                key={report.id}
                report={report}
                canExport={canExport}
                canShare={false}
              />
            ))
          )}
        </div>
      )}

      {tab === "approvals" && isAdmin && <ApprovalsQueue />}
    </div>
  );
}
