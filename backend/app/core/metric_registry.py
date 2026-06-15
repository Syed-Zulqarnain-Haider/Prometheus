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


@dataclass(frozen=True)
class Col:
    name: str
    bq_type: str  # BigQuery INFORMATION_SCHEMA data_type
    pg_type: str  # Postgres column type
    group: Group


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
    Col("pod",             "STRING",  "TEXT",    Group.DIMENSION),
    Col("pod_owner",       "STRING",  "TEXT",    Group.DIMENSION),
    Col("hou",             "STRING",  "TEXT",    Group.DIMENSION),
    Col("app_category",    "STRING",  "TEXT",    Group.DIMENSION),
    Col("ownership_type",  "STRING",  "TEXT",    Group.DIMENSION),
    Col("is_mapped",       "BOOL",    "BOOLEAN", Group.DIMENSION),

    # ── store installs ──────────────────────────────────────────────────────
    Col("store_first_time_installs", "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_redownloads",         "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_total_installs",      "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_organic_installs",    "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("gp_uninstalls",             "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("apple_restores",            "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("organic_install_share", "FLOAT64", "NUMERIC(12,6)", Group.STORE_INSTALLS),

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
    Col("cpi",          "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("fb_cpi",       "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("gads_cpi",     "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("mint_adv_cpi", "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("fb_ctr",       "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND),
    Col("gads_ctr",     "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND),
    Col("mint_adv_ctr", "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND),

    # ── ad revenue + derived ────────────────────────────────────────────────
    Col("admob_revenue_usd",    "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("admob_impressions",    "INT64",   "BIGINT",        Group.AD_REVENUE),
    Col("applovin_revenue_usd", "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("applovin_impressions", "INT64",   "BIGINT",        Group.AD_REVENUE),
    Col("total_ad_revenue_usd", "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("admob_ecpm",           "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("applovin_ecpm",        "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),

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
    Col("profit_usd",        "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("roas",              "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("ad_roas",           "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),

    # ── system ──────────────────────────────────────────────────────────────
    Col("_built_at", "TIMESTAMP", "TIMESTAMPTZ", Group.SYSTEM),
]
# fmt: on

COLUMN_NAMES: list[str] = [c.name for c in REGISTRY]


def columns_for_groups(groups: set[Group]) -> list[str]:
    """Column names belonging to any of the given metric groups."""
    return [c.name for c in REGISTRY if c.group in groups]
