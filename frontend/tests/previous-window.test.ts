import { previousWindow } from "@/lib/compare";

/** Days in an inclusive yyyy-MM-dd range, counted the calendar way. */
function lengthOf(from: string, to: string): number {
  const [fy, fm, fd] = from.split("-").map(Number);
  const [ty, tm, td] = to.split("-").map(Number);
  return Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(fy, fm - 1, fd)) / 86_400_000) + 1;
}

describe("previousWindow - the immediately-preceding window of equal length", () => {
  it("returns the adjacent prior week for a 7-day window", () => {
    expect(previousWindow("2026-07-08", "2026-07-14")).toEqual({
      from: "2026-07-01",
      to: "2026-07-07",
    });
  });

  it("ends exactly one day before the current window starts", () => {
    const prev = previousWindow("2026-08-15", "2026-08-21");
    expect(prev.to).toBe("2026-08-14");
  });

  it("crosses a month boundary correctly", () => {
    expect(previousWindow("2026-08-01", "2026-08-31")).toEqual({
      from: "2026-07-01",
      to: "2026-07-31",
    });
  });

  it("crosses a year boundary correctly", () => {
    expect(previousWindow("2026-01-01", "2026-01-07")).toEqual({
      from: "2025-12-25",
      to: "2025-12-31",
    });
  });

  it("handles the leap day", () => {
    // 2028 is a leap year; the window before Mar 1-2 must end on Feb 29.
    expect(previousWindow("2028-03-01", "2028-03-02")).toEqual({
      from: "2028-02-28",
      to: "2028-02-29",
    });
  });

  it("a single-day window maps to the single previous day", () => {
    expect(previousWindow("2026-03-01", "2026-03-01")).toEqual({
      from: "2026-02-28",
      to: "2026-02-28",
    });
  });

  it("preserves window length across DST-affected months", () => {
    // The old implementation subtracted raw 86400000ms blocks, which drifts a calendar day
    // when the window brackets a DST change (in TZs that observe it). Calendar arithmetic
    // must keep the previous window the same length and exactly adjacent, whatever TZ the
    // test happens to run in.
    for (const [from, to] of [
      ["2026-03-01", "2026-03-31"], // US spring-forward month
      ["2026-10-15", "2026-11-15"], // US fall-back straddle
      ["2026-03-20", "2026-04-05"], // EU spring-forward straddle
    ] as const) {
      const prev = previousWindow(from, to);
      expect(lengthOf(prev.from, prev.to)).toBe(lengthOf(from, to));
      expect(lengthOf(prev.to, from)).toBe(2); // adjacent: prev.to is the day before `from`
    }
  });

  it("tolerates timestamps, using only the date part", () => {
    expect(previousWindow("2026-07-08T09:30:00Z", "2026-07-14T23:59:59Z")).toEqual({
      from: "2026-07-01",
      to: "2026-07-07",
    });
  });
});
