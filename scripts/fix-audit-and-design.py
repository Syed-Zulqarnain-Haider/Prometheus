#!/usr/bin/env python3
"""Web-header hardening for the UpGuard findings that are actually fixable in code.

Four files:

  frontend/next.config.mjs            REPLACED - CSP, X-Frame-Options, X-Content-Type-
                                      Options, Referrer-Policy, Permissions-Policy,
                                      COOP, and poweredByHeader:false. The CSP folds in
                                      NEXT_PUBLIC_API_BASE_URL at build time so a split
                                      deployment does not lose every API call.
  frontend/tests/security-headers.ts  NEW - pins all of the above.
  docs/nginx-prometheus.conf          REPLACED - adds a default_server catch-all that
                                      returns 444, and stops /api/ carrying two HSTS
                                      headers (nginx's and the backend's).
  docs/SECURITY-REMEDIATION.md        NEW - every finding in the Aug 19 scan, split into
                                      what this repo fixed and what only the owner can.

next.config.mjs is replaced rather than patched, so it is checked FIRST: it must be the
config this project ships (an `output: "standalone"` next config whose only other keys
are ones we put there). Anything else and this aborts without writing, because replacing
a file somebody has customised would throw the customisation away.

Nothing is written unless every check passes. Safe to run twice.

The header change needs a FRONTEND REBUILD to take effect. The nginx file is a template
in docs/ - apply it on the host by hand, then `nginx -t` before reloading.
"""

import base64
import io
import re
import sys
import tarfile
from pathlib import Path

PAYLOAD = "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"

# Keys this project's next config is allowed to have. `output` is the repo's own;
# the other two are what this patch (or the earlier harden-web-headers pass) adds.
KNOWN_CONFIG_KEYS = {"output", "poweredByHeader", "headers"}


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


root = Path(".")
if not (root / "backend" / "app" / "main.py").exists():
    die("run this from the repository root (backend/app/main.py is missing)")

config_path = root / "frontend" / "next.config.mjs"
nginx_path = root / "docs" / "nginx-prometheus.conf"

if not config_path.exists():
    die(f"{config_path} not found")
config_text = config_path.read_text()

if 'output: "standalone"' not in config_text:
    die(
        f"{config_path}: no `output: \"standalone\"` - this is not the config this "
        "project ships, so replacing it would discard whatever is there. Send me the "
        "file and I will patch it instead."
    )

# Top-level keys of the nextConfig object literal, at exactly one indent level.
found_keys = set(re.findall(r"^  ([A-Za-z_$][\w$]*)\s*[:(]", config_text, re.M))
unexpected = sorted(found_keys - KNOWN_CONFIG_KEYS)
if unexpected:
    die(
        f"{config_path} has settings this patch does not know about: "
        f"{', '.join(unexpected)}. Replacing it would drop them. Send me the file."
    )

if nginx_path.exists():
    nginx_text = nginx_path.read_text()
    if "nginx reverse proxy for Prometheus" not in nginx_text:
        die(
            f"{nginx_path} is not the template this project ships - not overwriting "
            "somebody's live config."
        )

# ── the anomaly score (audit finding B4: "530.3 sigma") ─────────────────────────
# Anchored, not replaced: anomaly_service.py is generated by add-watchlist-anomalies and
# may carry the session-isolation rollback too, so only the two regions that compute the
# score are touched.
SVC = Path("backend/app/services/anomaly_service.py")
TESTS = Path("backend/tests/test_anomalies.py")

CONSTS_ANCHOR = "_MIN_BASELINE_DAYS = 10"
CONSTS_NEW = '_MIN_BASELINE_DAYS = 10\n\n# A robust z divides by the MAD, so a series that barely moves produces an enormous score\n# from a perfectly ordinary change: an app sitting at 300 installs a day with a MAD of 2\n# scores 100 sigma the day it does 600. Those are the "530.3 sigma" and "+78,628%" numbers\n# the dashboard was showing, and they are arithmetic, not insight.\n#\n# Two guards, doing different jobs:\n#   * the FLOOR decides whether a score means anything at all. If the spread is under 1% of\n#     the level, the series is flat at its own scale and there is no sigma to quote.\n#   * the CAP is presentational. Past this, "how many sigma" stops carrying information -\n#     40 and 400 both mean "nothing like its own history" - and a giant number crowds every\n#     real anomaly off the top of the list.\n_MIN_MAD_RATIO = 0.01\n_MAX_SCORE = 25.0'

SCORE_ANCHOR_START = "    mad = statistics.median([abs(v - median) for v in baseline])"
SCORE_ANCHOR_END = "return score, material and abs(score) >= z_threshold"
SCORE_NEW = '    mad = statistics.median([abs(v - median) for v in baseline])\n    # A flat series has no scale, so it has no score - and "almost flat" has no USABLE\n    # scale, which is the same answer. Saying so beats inventing a number that would sort\n    # to the top of every list forever.\n    if mad == 0 or mad < _MIN_MAD_RATIO * abs(median):\n        return None, material and deviation != 0\n\n    score = _MAD_TO_SIGMA * deviation / mad\n    # Clamp for reporting. The comparison against the threshold uses the CLAMPED value on\n    # purpose: the cap sits far above any sane threshold, so nothing that should fire stops\n    # firing, and nothing that fires can print an absurd number.\n    score = max(-_MAX_SCORE, min(_MAX_SCORE, score))\n    return score, material and abs(score) >= z_threshold'

TESTS_ADD = '\n\n# ── score sanity: the "530 sigma" bug ────────────────────────────────────────────\ndef test_a_barely_moving_series_gets_no_score_instead_of_a_huge_one() -> None:\n    """A robust z divides by the MAD, so a nearly flat series turns an ordinary change\n    into hundreds of sigma. Those numbers were arithmetic, not insight."""\n    from app.services.anomaly_service import _score\n\n    # 300/day with a MAD of 1 - under the 1% floor. Doubling is a real move, but there is\n    # no usable scale to express it in sigma, so there must be no score at all.\n    baseline = [300, 300, 301, 300, 299, 300, 300, 301, 300, 300, 299, 300]\n    score, _ = _score(600, baseline, z_threshold=3.5, min_change=0.2)\n    assert score is None\n\n\ndef test_a_score_is_never_absurd() -> None:\n    from app.services.anomaly_service import _MAX_SCORE, _score\n\n    # A series with real but small spread, and a violent jump.\n    baseline = [100, 140, 90, 130, 110, 95, 120, 105, 115, 100, 125, 108]\n    score, is_anomaly = _score(500_000, baseline, z_threshold=3.5, min_change=0.2)\n    assert score is not None\n    assert is_anomaly\n    assert abs(score) <= _MAX_SCORE\n\n\ndef test_a_genuine_anomaly_still_fires_and_keeps_its_sign() -> None:\n    from app.services.anomaly_service import _score\n\n    baseline = [100, 140, 90, 130, 110, 95, 120, 105, 115, 100, 125, 108]\n    up, up_hit = _score(400, baseline, z_threshold=3.5, min_change=0.2)\n    down, down_hit = _score(5, baseline, z_threshold=3.5, min_change=0.2)\n    assert up is not None and up > 0 and up_hit\n    assert down is not None and down < 0 and down_hit\n\n\ndef test_a_rounding_error_move_is_not_an_anomaly_however_improbable() -> None:\n    from app.services.anomaly_service import _score\n\n    baseline = [100, 140, 90, 130, 110, 95, 120, 105, 115, 100, 125, 108]\n    score, is_anomaly = _score(112, baseline, z_threshold=3.5, min_change=0.2)\n    assert not is_anomaly, score\n'


def patch_anomaly() -> None:
    if not SVC.exists():
        print(f"{SVC}: not present - skipping the anomaly fix")
        return
    text = SVC.read_text()
    if "_MIN_MAD_RATIO" in text:
        print(f"{SVC}: already fixed")
    else:
        if text.count(CONSTS_ANCHOR) != 1:
            die(f"{SVC}: expected exactly one {CONSTS_ANCHOR!r}")
        start = text.find(SCORE_ANCHOR_START)
        if start == -1:
            die(f"{SVC}: the MAD calculation was not found")
        end = text.find(SCORE_ANCHOR_END, start)
        if end == -1:
            die(f"{SVC}: the score return was not found")
        end += len(SCORE_ANCHOR_END)
        text = text[:start] + SCORE_NEW + text[end:]
        text = text.replace(CONSTS_ANCHOR, CONSTS_NEW, 1)
        SVC.write_text(text)
        print(f"patched {SVC}: MAD floor + score cap")

    if TESTS.exists():
        tests_text = TESTS.read_text()
        if "_MAX_SCORE" in tests_text:
            print(f"{TESTS}: already covered")
        else:
            TESTS.write_text(tests_text.rstrip("\n") + "\n" + TESTS_ADD)
            print(f"patched {TESTS}: score-sanity tests")


# ── the analytics-labelling findings (audit B5, B7) ─────────────────────────────
# Anchored, because these files drift between trees. Each is skipped if already applied
# and each anchor must match exactly once.
UI_MARKER_EDITS = [
    (
        "frontend/lib/format.ts",
        "formatUnitCost",
        [(
            '/** A fraction (0.704) rendered as a percentage ("70.4%"). */',
            '/** A per-unit cost: CPI, eCPM, cost-per-anything.\n *\n *  These are routinely SUB-CENT, and rounding them to two decimals is not a display\n *  choice - it is throwing the number away. A blended CPI of $0.0091 and one of $0.0140\n *  are a 54% difference in what a campaign costs, and both render as "$0.01". Precision\n *  follows magnitude: cents once the value is dollar-scale, more decimals below it. */\nexport function formatUnitCost(value: number | null | undefined): string {\n  if (isNil(value)) return EMPTY;\n  const magnitude = Math.abs(value);\n  const digits = magnitude === 0 || magnitude >= 1 ? 2 : magnitude >= 0.01 ? 3 : 4;\n  return new Intl.NumberFormat("en-US", {\n    style: "currency",\n    currency: "USD",\n    minimumFractionDigits: digits,\n    maximumFractionDigits: digits,\n  }).format(value);\n}\n\n' + '/** A fraction (0.704) rendered as a percentage ("70.4%"). */',
        )],
    ),
    (
        "frontend/components/overview/ratio-cards.tsx",
        "formatUnitCost",
        [
            (
                'import { formatMultiplier, formatUSD } from "@/lib/format";',
                'import { formatMultiplier, formatUnitCost } from "@/lib/format";',
            ),
            (
                '{ label: "CPI", field: "cpi", value: formatUSD(current.cpi, { digits: 2 }) }',
                '{ label: "CPI", field: "cpi", value: formatUnitCost(current.cpi) }',
            ),
        ],
    ),
    (
        "frontend/components/overview/kpi-row.tsx",
        '"TF Profit"',
        [(
            '{ label: "Gross Profit", field: "rpt_tf_profit_usd",',
            '{ label: "TF Profit", field: "rpt_tf_profit_usd",',
        )],
    ),
    (
        "frontend/components/overview/what-moved.tsx",
        '{ field: "rpt_tf_profit_usd", label: "TF Profit" }',
        [(
            '{ field: "rpt_tf_profit_usd", label: "Gross Profit" }',
            '{ field: "rpt_tf_profit_usd", label: "TF Profit" }',
        )],
    ),
]

FORMAT_TESTS = "frontend/tests/format.test.ts"
FORMAT_TEST_BLOCK = '\ndescribe("formatUnitCost", () => {\n  it("keeps sub-cent costs readable instead of rounding them to $0.01", () => {\n    // The real blended CPI was $0.00905 and the dashboard showed "$0.01" - which is also\n    // what $0.0140 showed, a 54% difference rendered identically.\n    expect(formatUnitCost(0.00905)).toBe("$0.0091");\n    expect(formatUnitCost(0.014)).toBe("$0.014");\n    expect(formatUnitCost(0.00905)).not.toBe(formatUnitCost(0.014));\n  });\n\n  it("uses cents once the value is dollar-scale", () => {\n    expect(formatUnitCost(1.5)).toBe("$1.50");\n    expect(formatUnitCost(12.345)).toBe("$12.35");\n    expect(formatUnitCost(0.5)).toBe("$0.500");\n  });\n\n  it("handles zero, null and undefined", () => {\n    expect(formatUnitCost(0)).toBe("$0.00");\n    expect(formatUnitCost(null)).toBe("");\n    expect(formatUnitCost(undefined)).toBe("");\n  });\n});\n'


def patch_ui() -> None:
    planned = []
    for rel, marker, pairs in UI_MARKER_EDITS:
        path = Path(rel)
        if not path.exists():
            print(f"{rel}: not present - skipping")
            continue
        text = path.read_text()
        if marker in text:
            print(f"{rel}: already applied")
            continue
        for anchor, _ in pairs:
            if text.count(anchor) != 1:
                die(f"{rel}: expected exactly one {anchor[:60]!r}, found {text.count(anchor)}")
        planned.append((path, text, pairs))
    for path, text, pairs in planned:
        for anchor, replacement in pairs:
            text = text.replace(anchor, replacement, 1)
        path.write_text(text)
        print(f"patched {path}")

    tests = Path(FORMAT_TESTS)
    if not tests.exists():
        return
    text = tests.read_text()
    if "formatUnitCost" in text:
        print(f"{FORMAT_TESTS}: already covered")
        return
    match = re.search(r'import \{([^}]*)\} from "@/lib/format";', text)
    if match is None:
        die(f"{FORMAT_TESTS}: no @/lib/format import to extend")
    names = sorted({n.strip() for n in match.group(1).split(",") if n.strip()} | {"formatUnitCost"})
    text = (
        text[: match.start()]
        + "import { " + ", ".join(names) + ' } from "@/lib/format";'
        + text[match.end() :]
    )
    tests.write_text(text.rstrip("\n") + "\n" + FORMAT_TEST_BLOCK)
    print(f"patched {FORMAT_TESTS}: formatUnitCost tests")


# ── consistent number formatting (visual pass V1) ───────────────────────────────
# One percent formatter and one table-currency formatter, instead of three local copies
# and a raw toFixed. Every edit is anchored and skipped when already applied.
V1_TABLE_FN = '/** Currency for a DENSE TABLE COLUMN, where being scannable beats being exact.\n *\n *  `formatUSD(v, {compact:true})` leaves Intl to decide, and Intl only compacts at or\n *  above a thousand - so one IAP column rendered "$11.04K" directly above "$311.67".\n *  Same column, two shapes, two decimal conventions: the eye cannot compare them.\n *\n *  One rule instead: a thousand and up is compact with a single decimal, below that is\n *  whole dollars. Cents are noise in a column whose other rows are millions, and every\n *  cell now has the same shape. */\nexport function formatTableUSD(value: number | null | undefined): string {\n  if (isNil(value)) return EMPTY;\n  if (Math.abs(value) >= 1000) {\n    return new Intl.NumberFormat("en-US", {\n      style: "currency",\n      currency: "USD",\n      notation: "compact",\n      minimumFractionDigits: 1,\n      maximumFractionDigits: 1,\n    }).format(value);\n  }\n  return new Intl.NumberFormat("en-US", {\n    style: "currency",\n    currency: "USD",\n    maximumFractionDigits: 0,\n  }).format(value);\n}\n\n'
V1_TABLE_TESTS = '\ndescribe("formatTableUSD", () => {\n  it("gives every cell in a column the same shape", () => {\n    // The reported bug: an IAP column rendered "$11.04K" directly above "$311.67" -\n    // two shapes and two decimal conventions in one column.\n    expect(formatTableUSD(11040)).toBe("$11.0K");\n    expect(formatTableUSD(311.67)).toBe("$312");\n    expect(formatTableUSD(302.34)).toBe("$302");\n  });\n\n  it("uses one decimal at every compact scale", () => {\n    expect(formatTableUSD(1000)).toBe("$1.0K");\n    expect(formatTableUSD(1_500_000)).toBe("$1.5M");\n    expect(formatTableUSD(2_300_000_000)).toBe("$2.3B");\n  });\n\n  it("handles the boundary, zero, negatives and nil", () => {\n    expect(formatTableUSD(999)).toBe("$999");\n    expect(formatTableUSD(0)).toBe("$0");\n    expect(formatTableUSD(-11040)).toBe("-$11.0K");\n    expect(formatTableUSD(null)).toBe("");\n    expect(formatTableUSD(undefined)).toBe("");\n  });\n});\n'
V1_DUP_OLD = 'function formatValue(unit: string, value: number): string {\n  if (unit === "usd") return formatUSD(value);\n  if (unit === "percent") return `${(value * 100).toFixed(1)}%`;\n  return `${value.toFixed(2)}×`;\n}'
V1_DUP_NEW = 'function formatValue(unit: string, value: number): string {\n  // Percent and multiplier go through the SHARED formatters. Two local copies of this\n  // function drifted from them and from each other, which is how one screen ended up\n  // showing "20.0%" beside "+104.19%".\n  if (unit === "usd") return formatUSD(value);\n  if (unit === "percent") return formatPercent(value);\n  return formatMultiplier(value);\n}'

V1_EDITS = [
    (
        "frontend/lib/format.ts",
        "formatTableUSD",
        [("/** A per-unit cost: CPI, eCPM, cost-per-anything.",
          V1_TABLE_FN + "/** A per-unit cost: CPI, eCPM, cost-per-anything.")],
    ),
    (
        "frontend/components/overview/revenue-table.tsx",
        "formatTableUSD",
        [
            ('import { formatCompact, formatMultiplier, formatUSD } from "@/lib/format";',
             'import { formatCompact, formatMultiplier, formatTableUSD } from "@/lib/format";'),
            ('  if (col.fmt === "usd") return formatUSD(v as number, { compact: true });',
             '  if (col.fmt === "usd") return formatTableUSD(v as number);'),
        ],
    ),
    ("frontend/components/overview/benchmarks-panel.tsx", "formatPercent(value)",
     [(V1_DUP_OLD, V1_DUP_NEW)]),
    ("frontend/components/app-detail/benchmark-card.tsx", "formatPercent(value)",
     [(V1_DUP_OLD, V1_DUP_NEW)]),
    ("frontend/components/overview/app-tape.tsx", "formatPercent(item.pct)",
     [("                        {(item.pct * 100).toFixed(2)}%",
       "                        {formatPercent(item.pct)}")]),
]

# Files whose "@/lib/format" import must gain names once their edit lands.
V1_IMPORT_NEEDS = {
    "frontend/components/overview/benchmarks-panel.tsx": ["formatPercent", "formatMultiplier"],
    "frontend/components/app-detail/benchmark-card.tsx": ["formatPercent", "formatMultiplier"],
    "frontend/components/overview/app-tape.tsx": ["formatPercent"],
}

FORMAT_IMPORT = re.compile(r'import \{([^}]*)\} from "@/lib/format";')


def _add_format_imports(text: str, rel: str, needed: list) -> str:
    """Extend the file's "@/lib/format" import, or add one if it has none.

    Adding is the common case for a file that never needed a formatter before - dying
    here would abort the whole patch over a missing import line.
    """
    match = FORMAT_IMPORT.search(text)
    if match is not None:
        names = sorted({n.strip() for n in match.group(1).split(",") if n.strip()} | set(needed))
        return (
            text[: match.start()]
            + "import { " + ", ".join(names) + ' } from "@/lib/format";'
            + text[match.end() :]
        )
    line = "import { " + ", ".join(sorted(set(needed))) + ' } from "@/lib/format";'
    lines = text.split("\n")
    # After the last aliased import, which is where the project's import order puts it.
    last = max(
        (i for i, ln in enumerate(lines) if ln.startswith("import ") and '"@/' in ln),
        default=None,
    )
    if last is None:
        last = max(
            (i for i, ln in enumerate(lines) if ln.startswith("import ")), default=-1
        )
    lines.insert(last + 1, line)
    return "\n".join(lines)


def patch_v1() -> None:
    planned = []
    for rel, marker, pairs in V1_EDITS:
        path = Path(rel)
        if not path.exists():
            print(f"{rel}: not present - skipping")
            continue
        text = path.read_text()
        if marker in text:
            print(f"{rel}: already consistent")
            continue
        for anchor, _ in pairs:
            if text.count(anchor) != 1:
                die(f"{rel}: expected exactly one {anchor[:60]!r}, found {text.count(anchor)}")
        planned.append((path, rel, text, pairs))
    for path, rel, text, pairs in planned:
        for anchor, replacement in pairs:
            text = text.replace(anchor, replacement, 1)
        if rel in V1_IMPORT_NEEDS:
            text = _add_format_imports(text, rel, V1_IMPORT_NEEDS[rel])
        path.write_text(text)
        print(f"patched {path}")

    tests = Path(FORMAT_TESTS)
    if not tests.exists():
        return
    text = tests.read_text()
    if "formatTableUSD" in text:
        print(f"{FORMAT_TESTS}: already covered")
        return
    text = _add_format_imports(text, FORMAT_TESTS, ["formatTableUSD"])
    tests.write_text(text.rstrip("\n") + "\n" + V1_TABLE_TESTS)
    print(f"patched {FORMAT_TESTS}: formatTableUSD tests")


# ── the design pass: contrast + one date format ─────────────────────────────────
# theme.css and the contrast test ship whole (in the payload); the date fix is anchored.
D2_ZONE_FN = '/** A timestamp WITH its timezone, for the "data as of" banner.\n *\n *  Two separate problems it solves. First, that banner used a raw `toLocaleString()`,\n *  so it rendered "18/08/2026, 17:54:39" while every other timestamp in the app read\n *  "Aug 19, 2026, 12:33 PM" - the only place in the product with its own date format.\n *  Second, and worse: the pipeline runs in UTC and the team reads it in Karachi, so a\n *  freshness time with no zone is a number nobody can act on. Say which clock it is. */\nexport function formatDateTimeWithZone(value: string | null | undefined): string {\n  if (!value) return EMPTY;\n  const date = new Date(value);\n  if (Number.isNaN(date.getTime())) return EMPTY;\n  // Spelled out component by component, NOT via dateStyle/timeStyle: Intl throws\n  // "Invalid option" if timeZoneName is combined with those. These options reproduce\n  // formatDateTime\'s medium/short output exactly, plus the zone.\n  return new Intl.DateTimeFormat("en-US", {\n    year: "numeric",\n    month: "short",\n    day: "numeric",\n    hour: "numeric",\n    minute: "2-digit",\n    timeZoneName: "short",\n  }).format(date);\n}\n\n'
D2_ZONE_TESTS = '\ndescribe("formatDateTimeWithZone", () => {\n  it("names the timezone, so a freshness time is actionable", () => {\n    const out = formatDateTimeWithZone("2026-08-19T12:33:00Z");\n    // A zone label is present (the exact abbreviation depends on the runner\'s zone).\n    expect(out).toMatch(/\\d{4}/);\n    expect(out.length).toBeGreaterThan(formatDateTime("2026-08-19T12:33:00Z").length);\n  });\n\n  it("matches the app\'s date style rather than inventing its own", () => {\n    // The banner used to render a raw toLocaleString, e.g. "18/08/2026, 17:54:39".\n    const out = formatDateTimeWithZone("2026-08-19T12:33:00Z");\n    expect(out).not.toMatch(/^\\d{2}\\/\\d{2}\\/\\d{4}/);\n    expect(out.startsWith(formatDateTime("2026-08-19T12:33:00Z").split(",")[0])).toBe(true);\n  });\n\n  it("is empty for nil and unparseable input", () => {\n    expect(formatDateTimeWithZone(null)).toBe("");\n    expect(formatDateTimeWithZone(undefined)).toBe("");\n    expect(formatDateTimeWithZone("not a date")).toBe("");\n  });\n});\n'

D2_EDITS = [
    (
        "frontend/lib/format.ts",
        "formatDateTimeWithZone",
        [("/** Escape a string for safe interpolation",
          D2_ZONE_FN + "/** Escape a string for safe interpolation")],
    ),
    (
        "frontend/components/layout/freshness-banner.tsx",
        "formatDateTimeWithZone",
        [("""  const builtAt = data.bq_built_at
    ? new Date(data.bq_built_at).toLocaleString()
    : "unknown";""",
          '  const builtAt = data.bq_built_at ? formatDateTimeWithZone(data.bq_built_at) : "unknown";')],
    ),
]


def patch_design() -> None:
    planned = []
    for rel, marker, pairs in D2_EDITS:
        path = Path(rel)
        if not path.exists():
            print(f"{rel}: not present - skipping")
            continue
        text = path.read_text()
        if marker in text:
            print(f"{rel}: already applied")
            continue
        for anchor, _ in pairs:
            if text.count(anchor) != 1:
                die(f"{rel}: expected exactly one {anchor[:60]!r}, found {text.count(anchor)}")
        planned.append((path, rel, text, pairs))
    for path, rel, text, pairs in planned:
        for anchor, replacement in pairs:
            text = text.replace(anchor, replacement, 1)
        if rel.endswith("freshness-banner.tsx"):
            text = _add_format_imports(text, rel, ["formatDateTimeWithZone"])
        path.write_text(text)
        print(f"patched {path}")

    tests = Path(FORMAT_TESTS)
    if not tests.exists():
        return
    text = tests.read_text()
    if "formatDateTimeWithZone" in text:
        print(f"{FORMAT_TESTS}: date format already covered")
        return
    text = _add_format_imports(text, FORMAT_TESTS, ["formatDateTimeWithZone", "formatDateTime"])
    tests.write_text(text.rstrip("\n") + "\n" + D2_ZONE_TESTS)
    print(f"patched {FORMAT_TESTS}: timezone tests")


# Every check passed; now write.
buffer = io.BytesIO(base64.b64decode(PAYLOAD))
with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
    names = tar.getnames()
    tar.extractall(root)
for name in names:
    print(f"wrote {name}")

print()
print("The header change takes effect on the next FRONTEND BUILD.")
print("docs/nginx-prometheus.conf is a template - apply it on the host, then:")
print("  sudo rm -f /etc/nginx/sites-enabled/default")
print("  sudo nginx -t && sudo systemctl reload nginx")
print()
print("docs/SECURITY-REMEDIATION.md lists the findings only you can close:")
print("  SPF/DMARC records, the FTP/IMAP/POP3 ports, and nginx/OpenSSH patching.")
patch_anomaly()
patch_ui()
patch_v1()
patch_design()
print("done")
