#!/usr/bin/env python3
"""Audit + design fixes: real CSP, sane anomaly scores, one formatting layer, WCAG AA.

Every edit is ANCHORED - no file is replaced wholesale, so a setting this patch does not
know about cannot be thrown away. If an anchor does not match, the script reports EVERY
mismatch it found and writes nothing, so one run tells you the whole story instead of one
problem at a time. Safe to re-run: each region is skipped once its marker is present.

What it changes:
  frontend/next.config.mjs        the CSP goes from "frame-ancestors 'none'" to a full
                                  policy; adds Cross-Origin-Opener-Policy. Everything else
                                  in that file is left exactly as it is.
  frontend/app/theme.css          15 colour tokens that fail WCAG AA are darkened/lightened
                                  along their own hue. The light theme's muted label sat at
                                  2.65:1; the COLOURBLIND theme had the weakest deltas of
                                  the lot (positive 3.10:1).
  frontend/lib/format.ts          one table-currency formatter (a column was mixing
                                  "$11.04K" with "$311.67"), one sub-cent unit-cost
                                  formatter (CPI showed $0.01 for $0.00905), one date
                                  formatter that names the timezone.
  ...and the call sites that had grown their own private copies of those formatters.
  backend/app/services/anomaly_service.py
                                  a MAD floor and a score cap, so "530.3 sigma" stops
                                  being a number the dashboard prints.
  new files                       contrast + header regression tests, and the remediation
                                  doc mapping every external-scan finding to an owner.
"""

import base64
import io
import re
import sys
import tarfile
from pathlib import Path

PAYLOAD = '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'

problems: list = []
planned: list = []


def stage(rel: str, marker: str, pairs: list, *, optional: bool = False) -> None:
    """Verify every anchor in one file; stage the result. Never writes."""
    path = Path(rel)
    if not path.exists():
        if not optional:
            problems.append(f"{rel}: file not found")
        return
    text = path.read_text()
    if marker in text:
        print(f"  = {rel}: already applied")
        return
    bad = []
    for anchor, _ in pairs:
        n = text.count(anchor)
        if n != 1:
            bad.append(f"      expected 1, found {n}:  {anchor.strip()[:78]!r}")
    if bad:
        problems.append(f"{rel}:\n" + "\n".join(bad))
        return
    for anchor, replacement in pairs:
        text = text.replace(anchor, replacement, 1)
    planned.append((path, text, rel))


FORMAT_IMPORT = re.compile(r'import \{([^}]*)\} from "@/lib/format";')


def add_format_imports(text: str, names: list) -> str:
    m = FORMAT_IMPORT.search(text)
    if m is not None:
        merged = sorted({n.strip() for n in m.group(1).split(",") if n.strip()} | set(names))
        return text[: m.start()] + "import { " + ", ".join(merged) + ' } from "@/lib/format";' + text[m.end():]
    line = "import { " + ", ".join(sorted(set(names))) + ' } from "@/lib/format";'
    lines = text.split("\n")
    last = max((i for i, ln in enumerate(lines) if ln.startswith("import ") and '"@/' in ln), default=None)
    if last is None:
        last = max((i for i, ln in enumerate(lines) if ln.startswith("import ")), default=-1)
    lines.insert(last + 1, line)
    return "\n".join(lines)


if not Path("backend/app/main.py").exists():
    sys.exit("ABORTED: run this from the repository root")

print("checking anchors...")

# ---- 1. the CSP -----------------------------------------------------------------
stage("frontend/next.config.mjs", "contentSecurityPolicy", [
    ("const securityHeaders = [", '// The API origin the browser will actually call. Behind nginx this is same-origin, but a\n// split deployment sets an absolute URL - and a CSP that forgot it would block every\n// request the dashboard makes and leave a page full of nothing.\nconst apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";\nconst apiOrigin = (() => {\n  try {\n    return apiBaseUrl ? new URL(apiBaseUrl).origin : "";\n  } catch {\n    return "";\n  }\n})();\n\n/** The full Content-Security-Policy.\n *\n *  `frame-ancestors \'none\'` alone stops clickjacking and nothing else - an external scan\n *  reports it as "CSP effectively absent", and it is. This adds the rest.\n *\n *  \'unsafe-inline\' in script-src is a MEASURED decision, not an oversight. A per-request\n *  nonce from middleware was built and tested against this app: Next.js serves these pages\n *  from the prerender cache, so the HTML carries no nonce while the header carries a fresh\n *  one. A browser IGNORES \'unsafe-inline\' once a nonce is present - measured in headless\n *  Chromium, 22 scripts refused and the page dead. It stays out until the nonce can reach\n *  the prerendered HTML. See docs/SECURITY-REMEDIATION.md.\n */\nconst contentSecurityPolicy = [\n  "default-src \'self\'",\n  "script-src \'self\' \'unsafe-inline\'",\n  "style-src \'self\' \'unsafe-inline\' https://fonts.googleapis.com",\n  "font-src \'self\' data: https://fonts.gstatic.com",\n  "img-src \'self\' data: blob: https:",\n  ["connect-src \'self\'", apiOrigin, "https://*.googleapis.com", "https://*.firebaseapp.com", "https://*.google.com"]\n    .filter(Boolean)\n    .join(" "),\n  "frame-src \'self\' https://*.firebaseapp.com https://*.google.com",\n  "frame-ancestors \'none\'",\n  "object-src \'none\'",\n  "base-uri \'self\'",\n  "form-action \'self\'",\n  "upgrade-insecure-requests",\n].join("; ");\n\n' + "const securityHeaders = ["),
    ('  { key: "Content-Security-Policy", value: "frame-ancestors \'none\'" },',
     '  { key: "Content-Security-Policy", value: contentSecurityPolicy },\n'
     '  // Isolate this browsing context from anything that opens it.\n'
     '  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },'),
])

# ---- 2. contrast ----------------------------------------------------------------
stage("frontend/app/theme.css", "#8d8168", [('  --color-text-muted:     #766c57;', '  --color-text-muted:     #8d8168;'), ('  --color-accent:        #cb5d50;', '  --color-accent:        #cd6256;'), ('  --color-negative:      #d4564b;', '  --color-negative:      #d55c51;'), ('  --color-text-muted:     #9a9485;', '  --color-text-muted:     #706b5d;'), ('  --color-text-primary:#e6eef7; --color-text-secondary:#9fb2c8; --color-text-muted:#6b7f96;', '  --color-text-primary:#e6eef7; --color-text-secondary:#9fb2c8; --color-text-muted:#788a9f;'), ('  --color-text-primary:#eaf0e0; --color-text-secondary:#a8b598; --color-text-muted:#74805f;', '  --color-text-primary:#eaf0e0; --color-text-secondary:#a8b598; --color-text-muted:#7f8c68;'), ('  --color-text-primary:#1a1a1a; --color-text-secondary:#4d4d4d; --color-text-muted:#767670;', '  --color-text-primary:#1a1a1a; --color-text-secondary:#4d4d4d; --color-text-muted:#6e6e69;'), ('  --color-negative:#d55e00; --color-negative-soft:rgba(213,94,0,.12);', '  --color-positive:#006449; --color-positive-soft:rgba(0,158,115,.13);'), ('  --color-text-primary:#e8eaed; --color-text-secondary:#a3a9b3; --color-text-muted:#6e747e;', '  --color-text-primary:#e8eaed; --color-text-secondary:#a3a9b3; --color-text-muted:#828892;'), ('  --color-accent:#c14d6b; --color-accent-strong:#a63d58; --color-accent-soft:rgba(193,77,107,.10);', '  --color-text-primary:#2a1e1e; --color-text-secondary:#6b5555; --color-text-muted:#826a6a;'), ('  --color-positive:#3d8a63; --color-positive-soft:rgba(61,138,99,.12);', '  --color-positive:#377c59; --color-positive-soft:rgba(61,138,99,.12);'), ('  --color-text-primary:#f2ecdb; --color-text-secondary:#b8ab8a; --color-text-muted:#82785d;', '  --color-text-primary:#f2ecdb; --color-text-secondary:#b8ab8a; --color-text-muted:#8f8467;'), ('  --color-text-primary:#ece7f4; --color-text-secondary:#afa4c4; --color-text-muted:#7a6f92;', '  --color-text-primary:#ece7f4; --color-text-secondary:#afa4c4; --color-text-muted:#89809f;')])

# ---- 3. the formatters ----------------------------------------------------------
stage("frontend/lib/format.ts", "formatTableUSD", [
    ("/** A fraction (0.704) rendered as a percentage (\"70.4%\"). */",
     '/** Currency for a DENSE TABLE COLUMN, where being scannable beats being exact.\n *\n *  `formatUSD(v, {compact:true})` leaves Intl to decide, and Intl only compacts at or\n *  above a thousand - so one IAP column rendered "$11.04K" directly above "$311.67".\n *  Same column, two shapes, two decimal conventions: the eye cannot compare them.\n *\n *  One rule instead: a thousand and up is compact with a single decimal, below that is\n *  whole dollars. Cents are noise in a column whose other rows are millions, and every\n *  cell now has the same shape. */\nexport function formatTableUSD(value: number | null | undefined): string {\n  if (isNil(value)) return EMPTY;\n  if (Math.abs(value) >= 1000) {\n    return new Intl.NumberFormat("en-US", {\n      style: "currency",\n      currency: "USD",\n      notation: "compact",\n      minimumFractionDigits: 1,\n      maximumFractionDigits: 1,\n    }).format(value);\n  }\n  return new Intl.NumberFormat("en-US", {\n    style: "currency",\n    currency: "USD",\n    maximumFractionDigits: 0,\n  }).format(value);\n}\n\n' + '/** A per-unit cost: CPI, eCPM, cost-per-anything.\n *\n *  These are routinely SUB-CENT, and rounding them to two decimals is not a display\n *  choice - it is throwing the number away. A blended CPI of $0.0091 and one of $0.0140\n *  are a 54% difference in what a campaign costs, and both render as "$0.01". Precision\n *  follows magnitude: cents once the value is dollar-scale, more decimals below it. */\nexport function formatUnitCost(value: number | null | undefined): string {\n  if (isNil(value)) return EMPTY;\n  const magnitude = Math.abs(value);\n  const digits = magnitude === 0 || magnitude >= 1 ? 2 : magnitude >= 0.01 ? 3 : 4;\n  return new Intl.NumberFormat("en-US", {\n    style: "currency",\n    currency: "USD",\n    minimumFractionDigits: digits,\n    maximumFractionDigits: digits,\n  }).format(value);\n}\n\n' + "/** A fraction (0.704) rendered as a percentage (\"70.4%\"). */"),
    ("/** Escape a string for safe interpolation", '/** A timestamp WITH its timezone, for the "data as of" banner.\n *\n *  Two separate problems it solves. First, that banner used a raw `toLocaleString()`,\n *  so it rendered "18/08/2026, 17:54:39" while every other timestamp in the app read\n *  "Aug 19, 2026, 12:33 PM" - the only place in the product with its own date format.\n *  Second, and worse: the pipeline runs in UTC and the team reads it in Karachi, so a\n *  freshness time with no zone is a number nobody can act on. Say which clock it is. */\nexport function formatDateTimeWithZone(value: string | null | undefined): string {\n  if (!value) return EMPTY;\n  const date = new Date(value);\n  if (Number.isNaN(date.getTime())) return EMPTY;\n  // Spelled out component by component, NOT via dateStyle/timeStyle: Intl throws\n  // "Invalid option" if timeZoneName is combined with those. These options reproduce\n  // formatDateTime\'s medium/short output exactly, plus the zone.\n  return new Intl.DateTimeFormat("en-US", {\n    year: "numeric",\n    month: "short",\n    day: "numeric",\n    hour: "numeric",\n    minute: "2-digit",\n    timeZoneName: "short",\n  }).format(date);\n}\n\n' + "/** Escape a string for safe interpolation"),
])

stage("frontend/components/overview/revenue-table.tsx", "formatTableUSD", [
    ('import { formatCompact, formatMultiplier, formatUSD } from "@/lib/format";',
     'import { formatCompact, formatMultiplier, formatTableUSD } from "@/lib/format";'),
    ('  if (col.fmt === "usd") return formatUSD(v as number, { compact: true });',
     '  if (col.fmt === "usd") return formatTableUSD(v as number);'),
])

DUP_OLD = 'function formatValue(unit: string, value: number): string {\n  if (unit === "usd") return formatUSD(value);\n  if (unit === "percent") return `${(value * 100).toFixed(1)}%`;\n  return `${value.toFixed(2)}×`;\n}'
DUP_NEW = 'function formatValue(unit: string, value: number): string {\n  // Percent and multiplier go through the SHARED formatters. Two local copies of this\n  // function drifted from them and from each other, which is how one screen ended up\n  // showing "20.0%" beside "+104.19%".\n  if (unit === "usd") return formatUSD(value);\n  if (unit === "percent") return formatPercent(value);\n  return formatMultiplier(value);\n}'
for rel in ("frontend/components/overview/benchmarks-panel.tsx",
            "frontend/components/app-detail/benchmark-card.tsx"):
    stage(rel, "formatPercent(value)", [(DUP_OLD, DUP_NEW)])

stage("frontend/components/overview/app-tape.tsx", "formatPercent(item.pct)", [
    ("                        {(item.pct * 100).toFixed(2)}%", "                        {formatPercent(item.pct)}"),
])

stage("frontend/components/overview/ratio-cards.tsx", "formatUnitCost", [
    ('import { formatMultiplier, formatUSD } from "@/lib/format";',
     'import { formatMultiplier, formatUnitCost } from "@/lib/format";'),
    ('{ label: "CPI", field: "cpi", value: formatUSD(current.cpi, { digits: 2 }) }',
     '{ label: "CPI", field: "cpi", value: formatUnitCost(current.cpi) }'),
])

stage("frontend/components/overview/kpi-row.tsx", '"TF Profit"', [
    ('{ label: "Gross Profit", field: "rpt_tf_profit_usd",', '{ label: "TF Profit", field: "rpt_tf_profit_usd",'),
])

stage("frontend/components/overview/what-moved.tsx", '{ field: "rpt_tf_profit_usd", label: "TF Profit" }', [
    ('{ field: "rpt_tf_profit_usd", label: "Gross Profit" }', '{ field: "rpt_tf_profit_usd", label: "TF Profit" }'),
])

stage("frontend/components/layout/freshness-banner.tsx", "formatDateTimeWithZone", [
    ("""  const builtAt = data.bq_built_at
    ? new Date(data.bq_built_at).toLocaleString()
    : "unknown";""",
     '  const builtAt = data.bq_built_at ? formatDateTimeWithZone(data.bq_built_at) : "unknown";'),
])

# ---- 4. the anomaly score -------------------------------------------------------
stage("backend/app/services/anomaly_service.py", "_MIN_MAD_RATIO", [
    ("_MIN_BASELINE_DAYS = 10", '_MIN_BASELINE_DAYS = 10\n\n# A robust z divides by the MAD, so a series that barely moves produces an enormous score\n# from a perfectly ordinary change: an app sitting at 300 installs a day with a MAD of 2\n# scores 100 sigma the day it does 600. Those are the "530.3 sigma" and "+78,628%" numbers\n# the dashboard was showing, and they are arithmetic, not insight.\n#\n# Two guards, doing different jobs:\n#   * the FLOOR decides whether a score means anything at all. If the spread is under 1% of\n#     the level, the series is flat at its own scale and there is no sigma to quote.\n#   * the CAP is presentational. Past this, "how many sigma" stops carrying information -\n#     40 and 400 both mean "nothing like its own history" - and a giant number crowds every\n#     real anomaly off the top of the list.\n_MIN_MAD_RATIO = 0.01\n_MAX_SCORE = 25.0'),
    ('    mad = statistics.median([abs(v - median) for v in baseline])\n    if mad == 0:\n        # A flat series. There is no scale, so there is no score - say so rather than\n        # inventing one that would sort to the top of every list forever.\n        return None, material and deviation != 0\n\n    score = _MAD_TO_SIGMA * deviation / mad\n    return score, material and abs(score) >= z_threshold', '    mad = statistics.median([abs(v - median) for v in baseline])\n    # A flat series has no scale, so it has no score - and "almost flat" has no USABLE\n    # scale, which is the same answer. Saying so beats inventing a number that would sort\n    # to the top of every list forever.\n    if mad == 0 or mad < _MIN_MAD_RATIO * abs(median):\n        return None, material and deviation != 0\n\n    score = _MAD_TO_SIGMA * deviation / mad\n    # Clamp for reporting. The comparison against the threshold uses the CLAMPED value on\n    # purpose: the cap sits far above any sane threshold, so nothing that should fire stops\n    # firing, and nothing that fires can print an absurd number.\n    score = max(-_MAX_SCORE, min(_MAX_SCORE, score))\n    return score, material and abs(score) >= z_threshold'),
])

if problems:
    print()
    print("ABORTED - nothing was written. These anchors did not match:")
    for p in problems:
        print("  * " + p)
    print()
    print("Send the block above back and I will re-anchor against your files.")
    raise SystemExit(1)

# ---- write ----------------------------------------------------------------------
IMPORT_NEEDS = {
    "frontend/components/overview/benchmarks-panel.tsx": ["formatPercent", "formatMultiplier"],
    "frontend/components/app-detail/benchmark-card.tsx": ["formatPercent", "formatMultiplier"],
    "frontend/components/overview/app-tape.tsx": ["formatPercent"],
    "frontend/components/layout/freshness-banner.tsx": ["formatDateTimeWithZone"],
}
for path, text, rel in planned:
    if rel in IMPORT_NEEDS:
        text = add_format_imports(text, IMPORT_NEEDS[rel])
    path.write_text(text)
    print(f"  + patched {rel}")

buf = io.BytesIO(base64.b64decode(PAYLOAD))
with tarfile.open(fileobj=buf, mode="r:gz") as tar:
    names = [n for n in tar.getnames() if n not in (".", "./")]
    tar.extractall(Path("."))
for n in names:
    if not n.endswith("/"):
        print(f"  + wrote {n.lstrip('./')}")

# ---- appended test blocks -------------------------------------------------------
ft = Path("frontend/tests/format.test.ts")
if ft.exists():
    t = ft.read_text()
    if "formatTableUSD" in t:
        print("  = frontend/tests/format.test.ts: already covered")
    else:
        t = add_format_imports(t, ["formatTableUSD", "formatUnitCost", "formatDateTimeWithZone", "formatDateTime"])
        ft.write_text(t.rstrip("\n") + "\n" + '\ndescribe("formatUnitCost", () => {\n  it("keeps sub-cent costs readable instead of rounding them to $0.01", () => {\n    // The real blended CPI was $0.00905 and the dashboard showed "$0.01" - which is also\n    // what $0.0140 showed, a 54% difference rendered identically.\n    expect(formatUnitCost(0.00905)).toBe("$0.0091");\n    expect(formatUnitCost(0.014)).toBe("$0.014");\n    expect(formatUnitCost(0.00905)).not.toBe(formatUnitCost(0.014));\n  });\n\n  it("uses cents once the value is dollar-scale", () => {\n    expect(formatUnitCost(1.5)).toBe("$1.50");\n    expect(formatUnitCost(12.345)).toBe("$12.35");\n    expect(formatUnitCost(0.5)).toBe("$0.500");\n  });\n\n  it("handles zero, null and undefined", () => {\n    expect(formatUnitCost(0)).toBe("$0.00");\n    expect(formatUnitCost(null)).toBe("");\n    expect(formatUnitCost(undefined)).toBe("");\n  });\n});\n\ndescribe("formatTableUSD", () => {\n  it("gives every cell in a column the same shape", () => {\n    // The reported bug: an IAP column rendered "$11.04K" directly above "$311.67" -\n    // two shapes and two decimal conventions in one column.\n    expect(formatTableUSD(11040)).toBe("$11.0K");\n    expect(formatTableUSD(311.67)).toBe("$312");\n    expect(formatTableUSD(302.34)).toBe("$302");\n  });\n\n  it("uses one decimal at every compact scale", () => {\n    expect(formatTableUSD(1000)).toBe("$1.0K");\n    expect(formatTableUSD(1_500_000)).toBe("$1.5M");\n    expect(formatTableUSD(2_300_000_000)).toBe("$2.3B");\n  });\n\n  it("handles the boundary, zero, negatives and nil", () => {\n    expect(formatTableUSD(999)).toBe("$999");\n    expect(formatTableUSD(0)).toBe("$0");\n    expect(formatTableUSD(-11040)).toBe("-$11.0K");\n    expect(formatTableUSD(null)).toBe("");\n    expect(formatTableUSD(undefined)).toBe("");\n  });\n});\n\ndescribe("formatDateTimeWithZone", () => {\n  it("names the timezone, so a freshness time is actionable", () => {\n    const out = formatDateTimeWithZone("2026-08-19T12:33:00Z");\n    // A zone label is present (the exact abbreviation depends on the runner\'s zone).\n    expect(out).toMatch(/\\d{4}/);\n    expect(out.length).toBeGreaterThan(formatDateTime("2026-08-19T12:33:00Z").length);\n  });\n\n  it("matches the app\'s date style rather than inventing its own", () => {\n    // The banner used to render a raw toLocaleString, e.g. "18/08/2026, 17:54:39".\n    const out = formatDateTimeWithZone("2026-08-19T12:33:00Z");\n    expect(out).not.toMatch(/^\\d{2}\\/\\d{2}\\/\\d{4}/);\n    expect(out.startsWith(formatDateTime("2026-08-19T12:33:00Z").split(",")[0])).toBe(true);\n  });\n\n  it("is empty for nil and unparseable input", () => {\n    expect(formatDateTimeWithZone(null)).toBe("");\n    expect(formatDateTimeWithZone(undefined)).toBe("");\n    expect(formatDateTimeWithZone("not a date")).toBe("");\n  });\n});\n')
        print("  + patched frontend/tests/format.test.ts")

at = Path("backend/tests/test_anomalies.py")
if at.exists():
    t = at.read_text()
    if "_MAX_SCORE" in t:
        print("  = backend/tests/test_anomalies.py: already covered")
    else:
        at.write_text(t.rstrip("\n") + "\n" + '\n\n# ── score sanity: the "530 sigma" bug ────────────────────────────────────────────\ndef test_a_barely_moving_series_gets_no_score_instead_of_a_huge_one() -> None:\n    """A robust z divides by the MAD, so a nearly flat series turns an ordinary change\n    into hundreds of sigma. Those numbers were arithmetic, not insight."""\n    from app.services.anomaly_service import _score\n\n    # 300/day with a MAD of 1 - under the 1% floor. Doubling is a real move, but there is\n    # no usable scale to express it in sigma, so there must be no score at all.\n    baseline = [300, 300, 301, 300, 299, 300, 300, 301, 300, 300, 299, 300]\n    score, _ = _score(600, baseline, z_threshold=3.5, min_change=0.2)\n    assert score is None\n\n\ndef test_a_score_is_never_absurd() -> None:\n    from app.services.anomaly_service import _MAX_SCORE, _score\n\n    # A series with real but small spread, and a violent jump.\n    baseline = [100, 140, 90, 130, 110, 95, 120, 105, 115, 100, 125, 108]\n    score, is_anomaly = _score(500_000, baseline, z_threshold=3.5, min_change=0.2)\n    assert score is not None\n    assert is_anomaly\n    assert abs(score) <= _MAX_SCORE\n\n\ndef test_a_genuine_anomaly_still_fires_and_keeps_its_sign() -> None:\n    from app.services.anomaly_service import _score\n\n    baseline = [100, 140, 90, 130, 110, 95, 120, 105, 115, 100, 125, 108]\n    up, up_hit = _score(400, baseline, z_threshold=3.5, min_change=0.2)\n    down, down_hit = _score(5, baseline, z_threshold=3.5, min_change=0.2)\n    assert up is not None and up > 0 and up_hit\n    assert down is not None and down < 0 and down_hit\n\n\ndef test_a_rounding_error_move_is_not_an_anomaly_however_improbable() -> None:\n    from app.services.anomaly_service import _score\n\n    baseline = [100, 140, 90, 130, 110, 95, 120, 105, 115, 100, 125, 108]\n    score, is_anomaly = _score(112, baseline, z_threshold=3.5, min_change=0.2)\n    assert not is_anomaly, score\n')
        print("  + patched backend/tests/test_anomalies.py")

print()
print("done. Frontend rebuild applies the header and formatting changes.")
