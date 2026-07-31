"""metric_registry.py — SINGLE SOURCE OF TRUTH for every column in the fact table.

This is the canonical backend copy referenced by CLAUDE.md contract rule #2.
Pydantic response models, RBAC column filters, and the fact-table definition are
generated from it. Its column set is kept in lockstep with the sync job's copy
(``sync/metric_registry.py``) by ``tests/test_metric_registry_parity.py`` — if the
two ever diverge, that test fails. To add a column: add ONE entry here, mirror it
in the sync registry, and add an Alembic migration.
"""

from dataclasses import dataclass
from enum import Enum


class Group(str, Enum):  # noqa: UP042 — mirror sync/metric_registry.py verbatim
    DIMENSION = "dimension"
    STORE_INSTALLS = "store_installs"
    UA_SPEND = "ua_spend"
    AD_REVENUE = "ad_revenue"
    IAP_REVENUE = "iap_revenue"
    ATTRIBUTION = "attribution"
    PROFITABILITY = "profitability"
    SYSTEM = "system"
    # BigQuery-discovered columns adopted by the admin schema-reconcile that have no curated
    # metric group yet. Granted to ADMINS ONLY (migration c9d0e1f2a3b4), so they never reach
    # a non-admin role. Not part of the static REGISTRY — carried by the dynamic store below.
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class Col:
    name: str
    bq_type: str  # BigQuery INFORMATION_SCHEMA data_type
    pg_type: str  # Postgres column type
    group: Group
    # BigQuery expression that PRODUCES this column from the raw source table (the sync reads
    # the table directly, no view). None = plain pass-through. Set for the CAST(pod) dimension
    # and every derived metric. Columns WITH a source_expr are computed by the loader, so the
    # schema-diff never expects/type-checks them against the raw table (see expected_bq_schema).
    # Kept identical to sync/metric_registry.py (drift-guarded by test_metric_registry_parity).
    source_expr: str | None = None


# fmt: off
REGISTRY: list[Col] = [
    # ── dimensions ──────────────────────────────────────────────────────────
    Col("date",            "DATE",    "DATE",    Group.DIMENSION),
    Col("platform",        "STRING",  "TEXT",    Group.DIMENSION),
    Col("canonical_key",   "STRING",  "TEXT",    Group.DIMENSION),
    Col("apple_id",        "INT64",   "BIGINT",  Group.DIMENSION),
    Col("ios_bundle_id",   "STRING",  "TEXT",    Group.DIMENSION),
    Col("android_package", "STRING",  "TEXT",    Group.DIMENSION),
    Col("app_name",        "STRING",  "TEXT",    Group.DIMENSION),
    Col("publisher",       "STRING",  "TEXT",    Group.DIMENSION),
    Col("developer",       "STRING",  "TEXT",    Group.DIMENSION),
    # pod is INT64 in the source; the serving layer treats it as text — cast it here.
    Col("pod",             "STRING",  "TEXT",    Group.DIMENSION,
        source_expr="CAST(pod AS STRING)"),
    Col("pod_owner",       "STRING",  "TEXT",    Group.DIMENSION),
    Col("hou",             "STRING",  "TEXT",    Group.DIMENSION),
    Col("app_category",    "STRING",  "TEXT",    Group.DIMENSION),
    Col("ownership_type",  "STRING",  "TEXT",    Group.DIMENSION),
    Col("is_mapped",       "BOOL",    "BOOLEAN", Group.DIMENSION),
    # store/console account dimensions (Console + account filters)
    Col("google_play_account", "STRING", "TEXT", Group.DIMENSION),
    Col("apple_account",       "STRING", "TEXT", Group.DIMENSION),
    Col("rpt_console",         "STRING", "TEXT", Group.DIMENSION),

    # ── store installs ──────────────────────────────────────────────────────
    Col("store_first_time_installs", "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_redownloads",         "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_total_installs",      "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_organic_installs",    "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("gp_uninstalls",             "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("apple_restores",            "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("organic_install_share", "FLOAT64", "NUMERIC(12,6)", Group.STORE_INSTALLS,
        source_expr="ROUND(SAFE_DIVIDE(store_organic_installs, store_total_installs), 6)"),

    # ── paid UA installs + spend + engagement + derived ────────────────────
    Col("fb_paid_installs",       "INT64",   "BIGINT",           Group.UA_SPEND),
    Col("gads_paid_installs",     "FLOAT64", "DOUBLE PRECISION", Group.UA_SPEND),
    Col("mint_adv_paid_installs", "INT64",   "BIGINT",           Group.UA_SPEND),
    Col("total_paid_installs",    "FLOAT64", "DOUBLE PRECISION", Group.UA_SPEND),
    Col("fb_spend_usd",         "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("fb_impressions",       "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("fb_clicks",            "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("fb_purchases",         "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("fb_purchase_value",    "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("gads_spend_usd",       "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("gads_impressions",     "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("gads_clicks",          "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("gads_conversions",     "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("gads_conversions_value","FLOAT64","NUMERIC(18,4)", Group.UA_SPEND),
    Col("mint_adv_spend_usd",   "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("mint_adv_impressions", "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("mint_adv_clicks",      "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("total_ua_spend_usd",   "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("cpi",          "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(total_ua_spend_usd, total_paid_installs), 4)"),
    Col("fb_cpi",       "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(fb_spend_usd, fb_paid_installs), 4)"),
    Col("gads_cpi",     "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(gads_spend_usd, gads_paid_installs), 4)"),
    Col("mint_adv_cpi", "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(mint_adv_spend_usd, mint_adv_paid_installs), 4)"),
    Col("fb_ctr",       "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(fb_clicks, fb_impressions), 6)"),
    Col("gads_ctr",     "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(gads_clicks, gads_impressions), 6)"),
    Col("mint_adv_ctr", "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(mint_adv_clicks, mint_adv_impressions), 6)"),

    # ── ad revenue + derived ────────────────────────────────────────────────
    Col("admob_revenue_usd",    "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("admob_impressions",    "INT64",   "BIGINT",        Group.AD_REVENUE),
    Col("applovin_revenue_usd", "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("applovin_impressions", "INT64",   "BIGINT",        Group.AD_REVENUE),
    Col("total_ad_revenue_usd", "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("admob_ecpm",           "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE,
        source_expr="ROUND(SAFE_DIVIDE(admob_revenue_usd, admob_impressions) * 1000, 4)"),
    Col("applovin_ecpm",        "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE,
        source_expr="ROUND(SAFE_DIVIDE(applovin_revenue_usd, applovin_impressions) * 1000, 4)"),

    # ── IAP revenue ─────────────────────────────────────────────────────────
    Col("gp_iap_gross_usd",      "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("gp_iap_refunds_usd",    "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("gp_google_fee_usd",     "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("gp_iap_net_usd",        "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("gp_revenue_status",     "STRING",  "TEXT",          Group.IAP_REVENUE),
    Col("apple_iap_gross_usd",   "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("apple_iap_refunds_usd", "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("apple_iap_net_usd",     "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("apple_fee_usd",         "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("apple_iap_purchases",   "INT64",   "BIGINT",        Group.IAP_REVENUE),
    Col("apple_revenue_status",  "STRING",  "TEXT",          Group.IAP_REVENUE),
    Col("total_iap_gross_usd",   "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("total_iap_net_usd",     "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),

    # ── attribution (Adjust) — data synced, no v1 dashboard features ────────
    Col("adjust_conversions",      "INT64", "BIGINT", Group.ATTRIBUTION),
    Col("adjust_attribution",      "INT64", "BIGINT", Group.ATTRIBUTION),
    Col("adjust_installs",         "INT64", "BIGINT", Group.ATTRIBUTION),
    Col("adjust_paid_installs",    "INT64", "BIGINT", Group.ATTRIBUTION),
    Col("adjust_organic_installs", "INT64", "BIGINT", Group.ATTRIBUTION),
    Col("adjust_reattributions",   "INT64", "BIGINT", Group.ATTRIBUTION),

    # ── profitability / headline ────────────────────────────────────────────
    Col("total_revenue_usd", "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("tech_cost_usd",     "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("profit_usd",        "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY,
        source_expr="ROUND(total_revenue_usd - total_ua_spend_usd, 4)"),
    Col("roas",              "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY,
        source_expr="ROUND(SAFE_DIVIDE(total_revenue_usd, total_ua_spend_usd), 4)"),
    Col("ad_roas",           "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY,
        source_expr="ROUND(SAFE_DIVIDE(total_ad_revenue_usd, total_ua_spend_usd), 4)"),

    # ── reported actual totals (rpt_*) — finance-authoritative figures the cards now show ──
    Col("rpt_gross_revenue_usd",     "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_ua_cost_usd",           "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("rpt_tf_profit_usd",         "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_shares_fees_taxes_usd", "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),

    # ── reported finance ladder (rpt_*), read straight from the source table ──────────────
    # The finance-authoritative figures the source already computes upstream — pass-through,
    # never recomputed here (owner decision to surface the reported ladder directly).
    Col("rpt_first_time_installs",       "INT64",   "BIGINT",        Group.STORE_INSTALLS),
    Col("rpt_redownloads",               "INT64",   "BIGINT",        Group.STORE_INSTALLS),
    Col("rpt_total_installs",            "INT64",   "BIGINT",        Group.STORE_INSTALLS),
    Col("rpt_organic_installs",          "INT64",   "BIGINT",        Group.STORE_INSTALLS),
    Col("rpt_ad_revenue_usd",            "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("rpt_ad_revenue_after_share_usd","FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("rpt_total_revenue_usd",         "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_net_revenue_usd",           "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_net_revenue_terafort_usd",  "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_gross_profit_usd",          "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_net_profit_usd",            "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_total_cost_usd",            "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_tax_fees_usd",              "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_withholding_tax_usd",       "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_store_fee_usd",             "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_partner_fees_usd",          "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_partner_share_app_usd",     "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_partner_share_transsion_usd","FLOAT64","NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_partner_share_usd",         "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_total_deductions_usd",      "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),

    # ── system ──────────────────────────────────────────────────────────────
    Col("_built_at", "TIMESTAMP", "TIMESTAMPTZ", Group.SYSTEM),
]
# fmt: on

COLUMN_NAMES: list[str] = [c.name for c in REGISTRY]

# ── Dynamic (BigQuery-discovered) columns ────────────────────────────────────────
# Populated at startup and after each admin schema-reconcile from the ``dynamic_columns``
# table. Always ``Group.UNCLASSIFIED`` (admin-only). The static REGISTRY above remains the
# curated source of truth; these are the additively-adopted extras.
_DYNAMIC: list[Col] = []


def set_dynamic_columns(cols: list[Col]) -> None:
    """Replace the in-memory dynamic-column set (idempotent). Callers that mutate this MUST
    also clear ``response_models.build_response_model``'s cache — use
    ``app.services.fact_schema.refresh_dynamic_registry`` which does both."""
    global _DYNAMIC
    _DYNAMIC = list(cols)


def dynamic_columns() -> list[Col]:
    return list(_DYNAMIC)


def effective_registry() -> list[Col]:
    """The static registry plus any active dynamic columns — what RBAC, response models and
    the query builder actually operate over."""
    return [*REGISTRY, *_DYNAMIC]


# Registry columns the BigQuery view may not expose yet — the sync defaults them to 0
# instead of failing, and the Integration tab's schema diff flags them as optional (not a
# blocking mismatch). Kept identical to sync/metric_registry.py (drift-guarded by
# tests/test_metric_registry_parity.py).
OPTIONAL_SOURCE_COLUMNS: set[str] = {
    "tech_cost_usd",
    # Newly surfaced from the source view; optional so the sync keeps working if the code
    # deploys before the updated daily_performance_v1 view. Type-aware defaults (0 for
    # numerics, NULL for text) are applied by the sync until the view exposes them.
    "google_play_account",
    "apple_account",
    "rpt_console",
    "rpt_gross_revenue_usd",
    "rpt_ua_cost_usd",
    "rpt_tf_profit_usd",
    "rpt_shares_fees_taxes_usd",
}


def expected_bq_schema() -> dict[str, str]:
    """Registry column name -> expected BigQuery INFORMATION_SCHEMA data_type. Used by the
    admin schema-diff to compare the live source against the registry (informational only).
    Computed columns (those with a source_expr — pod cast + derived metrics) are produced by
    the sync, not read from the source, so they are excluded here (never flagged as missing)."""
    return {c.name: c.bq_type for c in REGISTRY if c.source_expr is None}


def columns_for_groups(groups: set[Group]) -> list[str]:
    """Column names belonging to any of the given metric groups."""
    return [c.name for c in REGISTRY if c.group in groups]
