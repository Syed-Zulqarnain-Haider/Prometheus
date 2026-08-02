"use client";

import { CalendarClock, Send, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  type ReportScheduleCreate,
  useCreateSchedule,
  useDeleteSchedule,
  useReportSchedules,
  useRunScheduleNow,
} from "@/lib/api-hooks";

type Cadence = "daily" | "weekly" | "monthly";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function browserTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function describe(s: {
  cadence: Cadence;
  hour: number;
  day_of_week: number | null;
  day_of_month: number | null;
  fmt: string;
  timezone: string;
}): string {
  const time = `${String(s.hour).padStart(2, "0")}:00`;
  const when =
    s.cadence === "daily"
      ? "Daily"
      : s.cadence === "weekly"
        ? `Weekly on ${DOW[s.day_of_week ?? 0]}`
        : `Monthly on day ${s.day_of_month ?? 1}`;
  return `${when} at ${time} ${s.timezone} · ${s.fmt.toUpperCase()}`;
}

/** Schedule recurring email delivery of a report. Delivery always runs under — and is sent
 * only to — the owner, so it never becomes a way to share data around RBAC. */
export function ScheduleDialog({ reportId }: { reportId: string }) {
  const [open, setOpen] = useState(false);
  const schedules = useReportSchedules(reportId, open);
  const create = useCreateSchedule();
  const del = useDeleteSchedule();
  const runNow = useRunScheduleNow();

  const [cadence, setCadence] = useState<Cadence>("daily");
  const [hour, setHour] = useState(8);
  const [dow, setDow] = useState(0);
  const [dom, setDom] = useState(1);
  const [fmt, setFmt] = useState<"csv" | "xlsx">("xlsx");
  const [sentMsg, setSentMsg] = useState<string | null>(null);

  function submit() {
    const body: ReportScheduleCreate = {
      cadence,
      hour,
      fmt,
      timezone: browserTz(),
      day_of_week: cadence === "weekly" ? dow : null,
      day_of_month: cadence === "monthly" ? dom : null,
    };
    create.mutate({ reportId, body });
  }

  const rows = schedules.data ?? [];

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          create.reset();
          setSentMsg(null);
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <CalendarClock className="h-4 w-4" />
          Schedule
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 space-y-3">
        <p className="text-xs font-medium text-muted-foreground">
          Email this report to yourself on a schedule. It always reflects only your access.
        </p>

        {/* Existing schedules */}
        {rows.length > 0 && (
          <ul className="space-y-1.5">
            {rows.map((s) => (
              <li
                key={s.id}
                className="flex items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-xs"
              >
                <span className="min-w-0 truncate">{describe(s)}</span>
                <span className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    aria-label="Send now"
                    title="Send now"
                    className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                    onClick={() =>
                      runNow.mutate(s.id, {
                        onSuccess: (r) =>
                          setSentMsg(
                            r.sent
                              ? "Sent — check your inbox."
                              : "Email isn't configured on the server yet.",
                          ),
                      })
                    }
                    disabled={runNow.isPending}
                  >
                    <Send className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    aria-label="Delete schedule"
                    title="Delete"
                    className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
                    onClick={() => del.mutate({ reportId, scheduleId: s.id })}
                    disabled={del.isPending}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}

        {/* New schedule form */}
        <div className="grid grid-cols-2 gap-2">
          <Select value={cadence} onValueChange={(v) => setCadence(v as Cadence)}>
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="daily">Daily</SelectItem>
              <SelectItem value="weekly">Weekly</SelectItem>
              <SelectItem value="monthly">Monthly</SelectItem>
            </SelectContent>
          </Select>

          <Select value={String(hour)} onValueChange={(v) => setHour(Number(v))}>
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Array.from({ length: 24 }, (_, h) => (
                <SelectItem key={h} value={String(h)}>
                  {String(h).padStart(2, "0")}:00
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {cadence === "weekly" && (
            <Select value={String(dow)} onValueChange={(v) => setDow(Number(v))}>
              <SelectTrigger className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DOW.map((d, i) => (
                  <SelectItem key={d} value={String(i)}>
                    {d}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {cadence === "monthly" && (
            <Select value={String(dom)} onValueChange={(v) => setDom(Number(v))}>
              <SelectTrigger className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Array.from({ length: 28 }, (_, i) => (
                  <SelectItem key={i + 1} value={String(i + 1)}>
                    Day {i + 1}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          <Select value={fmt} onValueChange={(v) => setFmt(v as "csv" | "xlsx")}>
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="xlsx">XLSX</SelectItem>
              <SelectItem value="csv">CSV</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button size="sm" className="w-full" onClick={submit} disabled={create.isPending}>
          {create.isPending ? "Adding…" : "Add schedule"}
        </Button>

        {create.isError && (
          <p className="text-xs text-destructive">
            {create.error instanceof Error ? create.error.message : "Could not add schedule."}
          </p>
        )}
        {sentMsg && <p className="text-xs text-muted-foreground">{sentMsg}</p>}
        <p className="text-[11px] text-muted-foreground">
          Delivered to your account email, in {browserTz()}.
        </p>
      </PopoverContent>
    </Popover>
  );
}
