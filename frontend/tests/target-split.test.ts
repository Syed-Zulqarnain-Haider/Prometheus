import { MONTH_NUMBERS, redistribute, sumCents, toCents } from "@/lib/target-split";

/** The twelve months must add up to the annual figure exactly - that is the whole contract. */
function expectSumsTo(months: Record<number, string>, annual: string): void {
  expect(sumCents(months)).toBe(toCents(annual));
}

const NONE = new Set<number>();
const empty = (): Record<number, string> => ({});

describe("redistribute - annual target split across twelve months", () => {
  it("splits a clean annual evenly", () => {
    const out = redistribute("12000000", empty(), NONE);
    for (const m of MONTH_NUMBERS) expect(out[m]).toBe("1000000");
    expectSumsTo(out, "12000000");
  });

  it("lands exactly on the annual when it does not divide by twelve", () => {
    // 10,000,000 / 12 = 833,333.33... - the leftover cents have to go somewhere.
    const out = redistribute("10000000", empty(), NONE);
    expectSumsTo(out, "10000000");
  });

  it("lands exactly on the annual for an awkward amount", () => {
    const out = redistribute("1000000.07", empty(), NONE);
    expectSumsTo(out, "1000000.07");
  });

  it("holds a manual month fixed and spreads the rest over the other eleven", () => {
    const withJuly = { ...redistribute("12000000", empty(), NONE), 7: "3000000" };
    const out = redistribute("12000000", withJuly, new Set([7]));
    expect(out[7]).toBe("3000000"); // untouched
    // 9,000,000 left over eleven months = 818,181.81..., so the cents must still land exactly.
    for (const m of MONTH_NUMBERS.filter((n) => n !== 7)) expect(out[m]).not.toBe("3000000");
    expectSumsTo(out, "12000000");
  });

  it("keeps the total exact across several manual months", () => {
    const months = { ...redistribute("12000000", empty(), NONE), 1: "2000000", 6: "500000.55" };
    const out = redistribute("12000000", months, new Set([1, 6]));
    expect(out[1]).toBe("2000000");
    expect(out[6]).toBe("500000.55");
    expectSumsTo(out, "12000000");
  });

  it("zeroes the remaining months rather than going negative when manual months overshoot", () => {
    const months = { ...empty(), 1: "20000000" };
    const out = redistribute("12000000", months, new Set([1]));
    expect(out[1]).toBe("20000000");
    for (const m of MONTH_NUMBERS.filter((n) => n !== 1)) expect(out[m]).toBe("0");
    // The caller surfaces the overshoot; the panel must never render a negative target.
    expect(sumCents(out)).toBeGreaterThan(toCents("12000000") as number);
  });

  it("leaves everything alone when there is no annual target yet", () => {
    const months = { 1: "500", 2: "600" };
    expect(redistribute("", months, NONE)).toEqual(months);
    expect(redistribute("not a number", months, NONE)).toEqual(months);
  });

  it("leaves everything alone when every month is manual", () => {
    const months = Object.fromEntries(MONTH_NUMBERS.map((m) => [m, "1"]));
    const all = new Set(MONTH_NUMBERS);
    expect(redistribute("12000000", months, all)).toEqual(months);
  });

  it("hands a cleared month back to the automatic split", () => {
    const pinned = redistribute("12000000", { ...empty(), 7: "6000000" }, new Set([7]));
    expect(pinned[7]).toBe("6000000");
    const released = redistribute("12000000", { ...pinned, 7: "" }, NONE);
    for (const m of MONTH_NUMBERS) expect(released[m]).toBe("1000000");
    expectSumsTo(released, "12000000");
  });

  it("accepts amounts typed with thousands separators", () => {
    expect(toCents("12,000,000")).toBe(1200000000);
    expectSumsTo(redistribute("12,000,000", empty(), NONE), "12000000");
  });

  it("does not mutate the months it was given", () => {
    const months = { 1: "5" };
    const before = JSON.stringify(months);
    redistribute("12000000", months, NONE);
    expect(JSON.stringify(months)).toBe(before);
  });
});
