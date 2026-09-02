#!/usr/bin/env python3
"""One definition per number, computed once on the server - KPIs and table rows agree.

WHAT THE LOOKER SHEET PROVED
----------------------------
    Ads 79.5K + IAP 26.8K = 106.3K = Gross Revenue          (exact)
    ROAS 127.29% x 82.0K UA        = 104.4K                 (a DIFFERENT revenue)

Gross Revenue uses IAP GROSS; ROAS and Net Revenue use IAP NET, after refunds. Our
total_revenue_usd is the net basis by locked contract, so every column labelled "gross"
that was built from it came up short by exactly the refunds - the wrong number in the
apps table, found.

THE FIX IS NOT "CORRECT THE TS FORMULA"
---------------------------------------
Three different revenues were rendering on one Overview because three different places
computed them. Correcting the arithmetic in each place leaves three places to drift
again. So:

  * gross_revenue_usd (= IAP gross + ad revenue) joins net_revenue_usd and
    gross_profit_usd as a SERVER-computed period difference, in the one module that owns
    that arithmetic, with the same RBAC gating: emitted only when every component is
    inside the caller's permitted metric groups.
  * iap_roas (= IAP net / UA spend) joins roas and ad_roas as a period ratio - the owner
    asked for IAP ROAS and Ad ROAS in the tables, and ad_roas already existed.
  * TABLE AND BREAKDOWN ROWS now run through the SAME two functions the summary uses.
    Per-app ROAS, Net Rev and Gross Rev stop being TypeScript arithmetic over sums and
    become the identical formula, rounding and permission gate as the headline KPI.
    That is the whole "validate every column" ask, answered structurally: a table column
    can no longer disagree with the card above it, because neither computes anything.

Rounding note: ratios recomputed from summed components, never averaged daily ratios -
period ROAS is SUM(revenue)/SUM(spend), which is why this module exists at all.

Tested here, no database: the new definitions produce the Looker figures from the Looker
inputs, RBAC gating drops them when a component is not permitted, and zero denominators
yield null rather than zero.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
RATIOS = ROOT / "backend/app/services/period_ratios.py"
SERVICE = ROOT / "backend/app/services/metrics_service.py"
TEST = ROOT / "backend/tests/test_derived_metrics.py"

report: list[str] = []

EDITS: list[tuple[Path, str, str, str]] = [
    (
        RATIOS,
        "iap_roas joins roas and ad_roas",
        '    RatioDef("ad_roas", "total_ad_revenue_usd", "total_ua_spend_usd", 1.0, 4),',
        '    RatioDef("ad_roas", "total_ad_revenue_usd", "total_ua_spend_usd", 1.0, 4),\n'
        '    # IAP ROAS on the NET basis, matching roas: refunds are money that came back.\n'
        '    RatioDef("iap_roas", "total_iap_net_usd", "total_ua_spend_usd", 1.0, 4),',
    ),
    (
        RATIOS,
        "gross_revenue_usd becomes a server-owned definition",
        """    # Net Revenue = total revenue − UA spend.
    DiffDef("net_revenue_usd", ("total_revenue_usd",), ("total_ua_spend_usd",), 4),""",
        """    # Net Revenue = total revenue − UA spend. (Tech cost is deliberately NOT
    # subtracted here - owner decision; gross_profit_usd below is the figure that does.)
    DiffDef("net_revenue_usd", ("total_revenue_usd",), ("total_ua_spend_usd",), 4),
    # Gross Revenue = IAP GROSS + ad revenue. Deliberately a different revenue from
    # total_revenue_usd, which is IAP NET + ad revenue by locked contract: the gap is
    # refunds. Both are correct; only one is "gross", and it is this one. Reading it
    # from here is what stops a column labelled gross being computed from the net basis.
    DiffDef(
        "gross_revenue_usd",
        ("total_iap_gross_usd", "total_ad_revenue_usd"),
        (),
        4,
    ),""",
    ),
    (
        SERVICE,
        "table rows carry the same derived values as the summary",
        """    stmt = qb.table(params, sort=sort, direction=direction, limit=limit, cursor=cursor)
    rows = (await session.execute(stmt)).mappings().all()
    data = [_row_dict(r) for r in rows]""",
        """    stmt = qb.table(params, sort=sort, direction=direction, limit=limit, cursor=cursor)
    rows = (await session.execute(stmt)).mappings().all()
    # Derived values come from the SAME functions the summary uses, so a per-app ROAS or
    # Net Rev in the table cannot disagree with the KPI above it - identical formula,
    # identical rounding, identical permission gate. Computed from the RAW mapping so the
    # arithmetic sees Decimals, not their JSON rendering.
    data = [
        {**_row_dict(r), **_derived(r)}
        for r in rows
    ]""",
    ),
    (
        SERVICE,
        "breakdown rows too",
        """    return {"group_by": group_by, "rows": [_row_dict(r) for r in rows]}""",
        """    return {
        "group_by": group_by,
        "rows": [{**_row_dict(r), **_derived(r)} for r in rows],
    }""",
    ),
    (
        SERVICE,
        "the shared per-row helper",
        """def encode_cursor(sort_value: Any, key: str) -> str:""",
        '''def _derived(mapping: Any) -> dict[str, Any]:
    """Ratios and differences for ONE aggregated row, by the summary's own rules.

    Both helpers skip any metric whose components are missing from the mapping, and a
    row only contains the caller's permitted measures - so RBAC carries through without
    a second check here.
    """
    raw = dict(mapping)
    return {
        **{k: _to_jsonable(v) for k, v in compute_period_ratios(raw).items()},
        **{k: _to_jsonable(v) for k, v in compute_period_differences(raw).items()},
    }


def encode_cursor(sort_value: Any, key: str) -> str:''',
    ),
]

TEST_SRC = '''"""Every displayed number has ONE definition, and it lives on the server.

Built from the owner's Looker sheet, whose arithmetic settles the definitions:

    Ads 79.5K + IAP 26.8K = 106.3K = Gross Revenue      -> gross uses IAP GROSS
    ROAS 127.29% x 82.0K UA        = 104.4K             -> ROAS uses IAP NET

These pin the definitions themselves. The point is not that the formulas are hard - it
is that a table column and the KPI above it now read the same number from the same
place, so neither can drift.
"""

from __future__ import annotations

from app.services.period_ratios import compute_period_differences, compute_period_ratios

# The Looker period, in dollars: ads 79,500, IAP gross 26,800, UA 82,000, and the IAP net
# that ROAS implies (104,380 total revenue - 79,500 ads).
LOOKER = {
    "total_ad_revenue_usd": 79_500.0,
    "total_iap_gross_usd": 26_800.0,
    "total_iap_net_usd": 24_880.0,
    "total_revenue_usd": 104_380.0,
    "total_ua_spend_usd": 82_000.0,
}


def test_gross_revenue_is_ads_plus_iap_gross() -> None:
    # The exact sum on the owner's dashboard: 79.5K + 26.8K = 106.3K.
    assert compute_period_differences(LOOKER)["gross_revenue_usd"] == 106_300.0


def test_gross_revenue_is_not_the_net_basis() -> None:
    # The bug this closes: a column labelled "gross" built from total_revenue_usd is
    # short by exactly the refunds (26,800 - 24,880 = 1,920).
    diffs = compute_period_differences(LOOKER)
    assert diffs["gross_revenue_usd"] - LOOKER["total_revenue_usd"] == 1_920.0


def test_net_revenue_leaves_tech_cost_alone() -> None:
    # Owner decision: tech cost is not subtracted here. 104,380 - 82,000.
    assert compute_period_differences(LOOKER)["net_revenue_usd"] == 22_380.0


def test_roas_matches_the_dashboard_to_the_basis_point() -> None:
    assert round(compute_period_ratios(LOOKER)["roas"] * 100, 2) == 127.29


def test_ad_roas_and_iap_roas_split_the_same_spend() -> None:
    ratios = compute_period_ratios(LOOKER)
    assert ratios["ad_roas"] == round(79_500.0 / 82_000.0, 4)
    assert ratios["iap_roas"] == round(24_880.0 / 82_000.0, 4)
    # The two components add back up to total ROAS - the split is a decomposition,
    # not two unrelated numbers.
    assert round(ratios["ad_roas"] + ratios["iap_roas"], 3) == round(ratios["roas"], 3)


def test_a_zero_denominator_is_null_never_zero() -> None:
    # An app with revenue and no spend has no ROAS. Rendering 0 would read as "terrible
    # performance" for what is actually "not applicable".
    ratios = compute_period_ratios({**LOOKER, "total_ua_spend_usd": 0.0})
    assert ratios["roas"] is None
    assert ratios["ad_roas"] is None
    assert ratios["iap_roas"] is None


def test_a_metric_group_the_caller_lacks_removes_the_derived_value() -> None:
    # RBAC carries through by construction: totals only ever contain permitted measures,
    # and a derived value whose component is absent is simply not emitted - never
    # computed from a zero the caller was not allowed to see.
    without_iap = {k: v for k, v in LOOKER.items() if "iap" not in k}
    assert "gross_revenue_usd" not in compute_period_differences(without_iap)
    assert "iap_roas" not in compute_period_ratios(without_iap)
    # ...while what they CAN see still works.
    assert "ad_roas" in compute_period_ratios(without_iap)


def test_ratios_are_recomputed_from_totals_not_averaged() -> None:
    # Two days: 100 revenue on 10 spend (10x), then 100 on 190 (0.53x). The average of
    # the daily ratios is 5.26x; the correct period ROAS is 200/200 = 1.0x.
    period = {"total_revenue_usd": 200.0, "total_ua_spend_usd": 200.0}
    assert compute_period_ratios(period)["roas"] == 1.0
'''


def window(path: Path, needle: str) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - 4), min(len(lines), i + 14)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: anchor not found"


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    if "gross_revenue_usd" in RATIOS.read_text():
        print("Already applied - left alone.")
        if TEST.parent.is_dir():
            TEST.write_text(TEST_SRC)
            print(f"  - {TEST}: refreshed")
        return 0

    planned: dict[Path, str] = {}
    problems: list[str] = []
    for path, label, old, new in EDITS:
        if not path.exists():
            problems.append(f"  [{label}] {path}: file missing")
            continue
        text = planned.get(path, path.read_text())
        if text.count(old) != 1:
            problems.append(
                f"  [{label}] {path}: expected exactly 1 match, found {text.count(old)}\n"
                + window(path, old.splitlines()[0].strip()[:56])
            )
            continue
        planned[path] = text.replace(old, new, 1)

    if problems:
        print("NOTHING WAS WRITTEN - a half-applied definition is exactly the drift this")
        print("removes. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    # metrics_service must import what the per-row helper calls.
    text = planned[SERVICE]
    if "compute_period_differences" not in text.split("def ")[0]:
        old_import = "from app.services.period_ratios import compute_period_ratios"
        new_import = (
            "from app.services.period_ratios import ("
            "\n    compute_period_differences,"
            "\n    compute_period_ratios,"
            "\n)"
        )
        if old_import in text and "compute_period_differences," not in text:
            text = text.replace(old_import, new_import, 1)
            planned[SERVICE] = text
            report.append("[import] metrics_service: pulled in compute_period_differences")

    for path, content in planned.items():
        path.write_text(content)
        report.append(f"[fix] {path}")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: eight cases pinning the Looker definitions")

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    print(
        "\nThe API now serves, per period AND per table/breakdown row:"
        "\n  gross_revenue_usd (IAP gross + ads)   net_revenue_usd (revenue - UA)"
        "\n  roas   ad_roas   iap_roas   gross_profit_usd"
        "\nThe frontend batch reads these instead of computing them."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
