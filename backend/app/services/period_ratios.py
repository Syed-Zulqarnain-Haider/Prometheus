"""Period-level ratio KPIs, recomputed from aggregated totals.

Daily derived ratios (computed per-row in the BigQuery view) must NEVER be
averaged to produce a period figure. Instead, period ratios are recomputed from
the summed numerator/denominator — e.g. period ROAS = SUM(revenue)/SUM(spend).
A zero (or missing) denominator yields ``None`` (mirrors BigQuery SAFE_DIVIDE).

Formulas and rounding mirror ``sql/bigquery/daily_performance_v1.sql`` exactly,
plus ``profit_margin`` (owner-requested KPI = profit / revenue).

A ratio is only emitted when BOTH component totals are present in the input —
which, because totals come from the RBAC-filtered summary, keeps ratios behind
the same metric-group permissions as their components.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RatioDef:
    name: str
    numerator: str
    denominator: str
    scale: float
    ndigits: int


PERIOD_RATIOS: list[RatioDef] = [
    RatioDef("roas", "total_revenue_usd", "total_ua_spend_usd", 1.0, 4),
    RatioDef("ad_roas", "total_ad_revenue_usd", "total_ua_spend_usd", 1.0, 4),
    RatioDef("cpi", "total_ua_spend_usd", "total_paid_installs", 1.0, 4),
    RatioDef("fb_cpi", "fb_spend_usd", "fb_paid_installs", 1.0, 4),
    RatioDef("gads_cpi", "gads_spend_usd", "gads_paid_installs", 1.0, 4),
    RatioDef("mint_adv_cpi", "mint_adv_spend_usd", "mint_adv_paid_installs", 1.0, 4),
    RatioDef("admob_ecpm", "admob_revenue_usd", "admob_impressions", 1000.0, 4),
    RatioDef("applovin_ecpm", "applovin_revenue_usd", "applovin_impressions", 1000.0, 4),
    RatioDef("fb_ctr", "fb_clicks", "fb_impressions", 1.0, 6),
    RatioDef("gads_ctr", "gads_clicks", "gads_impressions", 1.0, 6),
    RatioDef("mint_adv_ctr", "mint_adv_clicks", "mint_adv_impressions", 1.0, 6),
    RatioDef("organic_install_share", "store_organic_installs", "store_total_installs", 1.0, 6),
    RatioDef("profit_margin", "profit_usd", "total_revenue_usd", 1.0, 6),
]


def compute_period_ratios(totals: Mapping[str, Any]) -> dict[str, float | None]:
    """Recompute ratio KPIs from summed totals; None on zero/absent denominator."""
    ratios: dict[str, float | None] = {}
    for r in PERIOD_RATIOS:
        if r.numerator not in totals or r.denominator not in totals:
            continue  # a component is outside the caller's permitted metrics
        denominator = totals[r.denominator]
        numerator = totals[r.numerator]
        if denominator is None or float(denominator) == 0.0:
            ratios[r.name] = None
        else:
            value = float(numerator or 0) * r.scale / float(denominator)
            ratios[r.name] = round(value, r.ndigits)
    return ratios


@dataclass(frozen=True)
class DiffDef:
    name: str
    add: tuple[str, ...]
    sub: tuple[str, ...]
    ndigits: int


# Headline difference KPIs, summed component-by-component then combined (so they
# stay period-correct). Like the ratios, each is emitted only when EVERY component
# is present in the RBAC-filtered totals — so they inherit metric-group permissions.
PERIOD_DIFFERENCES: list[DiffDef] = [
    # Net Revenue = total revenue − UA spend.
    DiffDef("net_revenue_usd", ("total_revenue_usd",), ("total_ua_spend_usd",), 4),
    # Gross Profit = (IAP gross + ad revenue) − UA spend − tech cost.
    DiffDef(
        "gross_profit_usd",
        ("total_iap_gross_usd", "total_ad_revenue_usd"),
        ("total_ua_spend_usd", "tech_cost_usd"),
        4,
    ),
]


def compute_period_differences(totals: Mapping[str, Any]) -> dict[str, float]:
    """Combine summed components into headline difference KPIs (net rev, gross profit).

    Emitted only when every component is permitted/present, so RBAC is preserved.
    """
    out: dict[str, float] = {}
    for d in PERIOD_DIFFERENCES:
        components = d.add + d.sub
        if any(c not in totals for c in components):
            continue
        value = sum(float(totals[c] or 0) for c in d.add) - sum(
            float(totals[c] or 0) for c in d.sub
        )
        out[d.name] = round(value, d.ndigits)
    return out
