"""
metric_registry.py — SINGLE SOURCE OF TRUTH for every column in daily_performance_v1.

Everything is generated from this file:
  • the Postgres fact-table / staging DDL        (generate_fact_ddl)
  • the sync job's BigQuery schema validation    (expected_bq_schema)
  • (later) Pydantic response models + RBAC column filters in the API

Adding a column to the BQ view = add ONE entry here + run a migration. Nothing else.
Removing/renaming a view column without updating this file → sync halts with
'schema_mismatch' and serves yesterday's data (never loads garbage).
"""
from dataclasses import dataclass
from enum import Enum


class Group(str, Enum):
    DIMENSION = "dimension"
    STORE_INSTALLS = "store_installs"
    UA_SPEND = "ua_spend"
    AD_REVENUE = "ad_revenue"
    IAP_REVENUE = "iap_revenue"
    ATTRIBUTION = "attribution"
    PROFITABILITY = "profitability"
    SYSTEM = "system"
    # BigQuery-discovered columns adopted by the admin schema-reconcile with no curated
    # metric group yet (admin-only on the serving side). Mirrors the backend registry.
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class Col:
    name: str
    bq_type: str   # BigQuery INFORMATION_SCHEMA data_type
    pg_type: str   # Postgres column type
    group: Group
    # BigQuery expression that PRODUCES this column from the raw source table when the
    # sync reads the table directly (no view). None = plain pass-through (the source has a
    # column of this exact name). Set for the CAST(pod) dimension and every derived metric
    # (roas/profit/cpi/ecpm/ctr/organic_install_share) — the finance math the view used to
    # hold now lives here, so bypassing the view never drops a metric. Columns WITH a
    # source_expr are never expected to exist in the source, so schema validation/diff skip
    # them (see expected_bq_schema).
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
    # pod is INT64 in the source; the serving layer treats it as text (dim/group/filter),
    # so cast it here (the view used to do this).
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

# Columns the registry knows about but the BigQuery view may not expose yet. When
# absent from the view, the sync defaults them to 0 instead of halting with a
# schema_mismatch. (tech_cost_usd: the data team will add the real field; until
# then we treat it as 0 so Gross Profit degrades gracefully rather than breaking.)
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


def optional_default_expr(name: str) -> str:
    """SQL literal for an optional source column the view doesn't expose yet, matched to the
    column's BigQuery type so the staging COPY stays type-correct (0 for numerics, typed NULL
    for text/bool/timestamp). Prevents a text dimension from being loaded as a numeric 0."""
    bq = {c.name: c.bq_type for c in REGISTRY}.get(name, "FLOAT64")
    if bq == "STRING":
        return f"CAST(NULL AS STRING) AS {name}"
    if bq == "BOOL":
        return f"CAST(NULL AS BOOL) AS {name}"
    if bq == "INT64":
        return f"CAST(0 AS INT64) AS {name}"
    if bq == "TIMESTAMP":
        return f"CAST(NULL AS TIMESTAMP) AS {name}"
    return f"CAST(0 AS FLOAT64) AS {name}"


# name -> BigQuery expression that produces each computed column from the raw source table.
# Used by the loader to build the SELECT; columns not here are plain pass-through.
SOURCE_EXPR: dict[str, str] = {
    c.name: c.source_expr for c in REGISTRY if c.source_expr is not None
}


def expected_bq_schema() -> dict[str, str]:
    """name -> BQ data_type, for INFORMATION_SCHEMA validation. Only pass-through columns are
    expected to exist in the source; computed columns (SOURCE_EXPR) are produced by the loader
    and must never be required in — or type-checked against — the raw table."""
    return {c.name: c.bq_type for c in REGISTRY if c.source_expr is None}


def columns_for_groups(groups: set[Group]) -> list[str]:
    """Used later by the API to build per-role response models."""
    return [c.name for c in REGISTRY if c.group in groups]


def generate_fact_ddl(table_name: str, with_pk: bool = True) -> str:
    """Emit CREATE TABLE for the fact/staging table, plus the generated app_key
    column used as part of the primary key (expressions aren't allowed in PKs).

    ``with_pk=False`` is used for the STAGING table: it omits the primary key so the load
    COPY can never crash on a duplicate natural key coming from the source (the sync
    collapses staging to one row per key before merging — see ``generate_merge_rows_sql``).
    The LIVE fact table always keeps its primary key, which the UPSERT relies on."""
    cols = ",\n  ".join(f"{c.name} {c.pg_type}" for c in REGISTRY)
    pk = ",\n  PRIMARY KEY (date, platform, app_key)" if with_pk else ""
    return f"""CREATE TABLE {table_name} (
  {cols},
  app_key TEXT GENERATED ALWAYS AS (
    COALESCE(canonical_key, android_package, CAST(apple_id AS TEXT), 'unknown')
  ) STORED{pk}
);"""


def generate_dedupe_sql(staging_table: str) -> str:
    """DEPRECATED — superseded by ``generate_merge_rows_sql``. Retained only so any other
    importer keeps working; the sync no longer calls it.

    This DISCARDED every row but the richest per (date, platform, app_key), which was correct
    only while the extra rows were believed to be accidental duplicates. They are not: the
    source emits one row per app-day PER CHANNEL (``store``/Google Play and ``dlight``/
    Dlightek). Discarding them silently lost ~1.5% of gross revenue every month, along with
    the installs, UA spend and ad revenue carried on those rows."""
    return f"""DELETE FROM {staging_table} s
USING (
    SELECT ctid, row_number() OVER (
        PARTITION BY date, platform, app_key
        ORDER BY total_revenue_usd DESC NULLS LAST,
                 store_total_installs DESC NULLS LAST,
                 ctid
    ) AS rn
    FROM {staging_table}
) d
WHERE s.ctid = d.ctid AND d.rn > 1"""


# Postgres expressions that RECOMPUTE each derived column from the SUMMED components when
# several source rows collapse into one. These mirror SOURCE_EXPR (the BigQuery side) —
# SAFE_DIVIDE becomes NULLIF-guarded division, which yields NULL on a zero denominator
# exactly as BigQuery does. Without this, merging would ADD ratios together (two rows at
# ROAS 4.7 becoming 9.4), so every non-dimension source_expr column MUST appear here;
# ``_assert_merge_coverage`` enforces that at import time.
_MERGE_RECOMPUTE: dict[str, str] = {
    "organic_install_share":
        "ROUND(SUM(store_organic_installs)::numeric "
        "/ NULLIF(SUM(store_total_installs), 0), 6)",
    "cpi":
        "ROUND((SUM(total_ua_spend_usd) "
        "/ NULLIF(SUM(total_paid_installs), 0))::numeric, 4)",
    "fb_cpi":
        "ROUND((SUM(fb_spend_usd) / NULLIF(SUM(fb_paid_installs), 0))::numeric, 4)",
    "gads_cpi":
        "ROUND((SUM(gads_spend_usd) / NULLIF(SUM(gads_paid_installs), 0))::numeric, 4)",
    "mint_adv_cpi":
        "ROUND((SUM(mint_adv_spend_usd) "
        "/ NULLIF(SUM(mint_adv_paid_installs), 0))::numeric, 4)",
    "fb_ctr":
        "ROUND(SUM(fb_clicks)::numeric / NULLIF(SUM(fb_impressions), 0), 6)",
    "gads_ctr":
        "ROUND(SUM(gads_clicks)::numeric / NULLIF(SUM(gads_impressions), 0), 6)",
    "mint_adv_ctr":
        "ROUND(SUM(mint_adv_clicks)::numeric / NULLIF(SUM(mint_adv_impressions), 0), 6)",
    "admob_ecpm":
        "ROUND((SUM(admob_revenue_usd) "
        "/ NULLIF(SUM(admob_impressions), 0) * 1000)::numeric, 4)",
    "applovin_ecpm":
        "ROUND((SUM(applovin_revenue_usd) "
        "/ NULLIF(SUM(applovin_impressions), 0) * 1000)::numeric, 4)",
    "profit_usd":
        "ROUND(SUM(total_revenue_usd) - SUM(total_ua_spend_usd), 4)",
    "roas":
        "ROUND((SUM(total_revenue_usd) / NULLIF(SUM(total_ua_spend_usd), 0))::numeric, 4)",
    "ad_roas":
        "ROUND((SUM(total_ad_revenue_usd) "
        "/ NULLIF(SUM(total_ua_spend_usd), 0))::numeric, 4)",
}

# Postgres types that are safe to SUM. Anything else collapses to one representative value
# instead (text dimensions, booleans, timestamps).
_ADDITIVE_PG_PREFIXES = ("BIGINT", "INTEGER", "SMALLINT", "NUMERIC", "DOUBLE", "REAL")

# The grain the merge collapses to — the live fact table's primary key. ``app_key`` is a
# generated column, so it is grouped on but never selected (it re-derives on insert).
MERGE_GROUP_BY = ("date", "platform", "app_key")


def _assert_merge_coverage() -> None:
    """Every derived (source_expr) column that isn't a dimension must have a merge rule — a
    new ratio added to the registry without one would otherwise be silently SUMMED."""
    missing = sorted(
        c.name
        for c in REGISTRY
        if c.source_expr is not None
        and c.group is not Group.DIMENSION
        and c.name not in _MERGE_RECOMPUTE
    )
    if missing:
        raise RuntimeError(
            "metric_registry: derived column(s) without a _MERGE_RECOMPUTE rule "
            f"(they would be summed, which is wrong for a ratio): {', '.join(missing)}"
        )


_assert_merge_coverage()


def _merge_term(name: str, pg_type: str, group: Group, quote: bool = False) -> str:
    """How ONE column collapses when several source rows for the same app-day are merged."""
    if name in MERGE_GROUP_BY:
        return name  # a grouping key — selected as-is, never aggregated
    if name in _MERGE_RECOMPUTE:
        return f"{_MERGE_RECOMPUTE[name]} AS {name}"
    ref = f'"{name}"' if quote else name
    upper = pg_type.upper()
    if upper.startswith("BOOL"):
        return f"bool_or({ref}) AS {ref}"  # MAX() is not defined for boolean in Postgres
    if group in (Group.DIMENSION, Group.SYSTEM) or not upper.startswith(_ADDITIVE_PG_PREFIXES):
        # Identity/label columns agree across merged rows (same app, same day). The one
        # exception is rpt_console, which names the channel — one value is kept.
        return f"MAX({ref}) AS {ref}"
    return f"SUM({ref}) AS {ref}"


def generate_merge_rows_sql(
    staging_table: str, extra_columns: list[tuple[str, str]] | None = None
) -> list[str]:
    """Collapse every source row for the same (date, platform, app_key) into ONE row by
    SUMMING the measures — never by discarding rows.

    The source emits one row per app-day **per channel** (e.g. ``store`` / Google Play and
    ``dlight`` / Dlightek). Those are distinct real revenue, not duplicates. The previous
    behaviour kept only the richest row, which silently lost ~1.5% of gross revenue every
    month — and with it the installs, UA spend and ad revenue on the discarded rows, since
    the surviving row supplied every column.

    Additive measures are SUMMED; identity/label columns collapse to one value; and every
    derived ratio (``roas``, ``cpi``, ``*_ctr``, ``*_ecpm``, ``profit_usd``,
    ``organic_install_share``) is RECOMPUTED from the summed components — adding ratios
    together would be meaningless.

    Staging is rewritten in place, so the generated ``app_key`` column re-derives itself from
    the collapsed identity columns. That is safe by construction: rows only share an app_key
    when the COALESCE resolves to the same value, so MAX() of those columns reproduces it.

    Returned as an ordered list of statements — the caller runs them in sequence, which keeps
    this compatible with psycopg's one-statement-per-execute default.
    """
    extra = extra_columns or []
    terms = [_merge_term(c.name, c.pg_type, c.group) for c in REGISTRY]
    terms += [_merge_term(n, t, Group.UNCLASSIFIED, quote=True) for n, t in extra]
    cols = ", ".join([*COLUMN_NAMES, *[f'"{n}"' for n, _ in extra]])
    tmp = f"{staging_table}_merged"
    return [
        f"DROP TABLE IF EXISTS {tmp}",
        f"CREATE TEMP TABLE {tmp} AS SELECT {', '.join(terms)} "
        f"FROM {staging_table} GROUP BY date, platform, app_key",
        f"DELETE FROM {staging_table}",
        f"INSERT INTO {staging_table} ({cols}) SELECT {cols} FROM {tmp}",
        f"DROP TABLE {tmp}",
    ]


# The natural key the daily sync UPSERTs on — the fact table's primary key. app_key is a
# generated column (COALESCE of canonical_key / android_package / apple_id), so this
# triple uniquely identifies one app's row for one day across iOS + Android.
UPSERT_KEY = ("date", "platform", "app_key")


def generate_upsert_sql(
    fact_table: str, staging_table: str, extra_columns: list[str] | None = None
) -> str:
    """Emit the INSERT…SELECT…ON CONFLICT that merges a freshly loaded staging table
    into the live fact table, keyed on (date, platform, app_key).

    Re-running a date UPDATES the existing rows in place (every non-key column refreshed
    to the latest values — so the Apple 2-3 day lag self-corrects); a new date APPENDS;
    rows already in the fact table but absent from staging are RETAINED. The fact table
    therefore accumulates full history even after BigQuery ages older days out — never a
    destructive replace.

    ``extra_columns`` are BigQuery-discovered dynamic columns (identifier-safe) present in
    BOTH staging and fact for this run; they are merged exactly like registry columns."""
    all_cols = [*COLUMN_NAMES, *(extra_columns or [])]
    cols = ", ".join(all_cols)
    # app_key is generated (never in COLUMN_NAMES); date/platform are the key, not updated.
    key = set(UPSERT_KEY)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in all_cols if c not in key)
    conflict = ", ".join(UPSERT_KEY)
    return (
        f"INSERT INTO {fact_table} ({cols})\n"
        f"SELECT {cols} FROM {staging_table}\n"
        f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    )


# Columns covered by the date-leading covering index (idx_fact_cover) so the hot,
# uncached Overview aggregates (summary / timeseries / breakdown / table) run as
# INDEX-ONLY scans instead of scattered heap reads. Under production-like (uncorrelated)
# physical order a 30-day window touches ~almost every heap page; the covering index
# turns that into a contiguous index-only slice (~16x fewer buffer reads, results
# unchanged). The set is the group/table dimensions + the Overview's headline additive
# measures, curated to stay well under Postgres's 32-column-per-index limit (a single
# index cannot cover all ~50 additive measures).
COVER_INDEX_COLUMNS = [
    # dimensions used for scope filters, GROUP BY, and the table endpoint's max()
    "canonical_key", "platform", "apple_id", "android_package", "app_name",
    "publisher", "pod", "pod_owner", "hou",
    # headline additive measures (KPIs, donuts, trend, splits, revenue tables)
    "store_total_installs", "store_organic_installs", "total_paid_installs",
    "total_revenue_usd", "total_ua_spend_usd", "total_ad_revenue_usd",
    "total_iap_gross_usd", "total_iap_net_usd", "tech_cost_usd", "profit_usd",
]


def generate_indexes(table_name: str, suffix: str = "") -> list[str]:
    """Index DDL. `suffix` lets the staging table use non-conflicting names;
    they are renamed to canonical names after the atomic swap."""
    cover = f"(date) INCLUDE ({', '.join(COVER_INDEX_COLUMNS)})"
    specs = [
        ("idx_fact_date",      "(date)"),
        ("idx_fact_canonical", "(canonical_key, date)"),
        ("idx_fact_pod",       "(pod, date)"),
        ("idx_fact_hou",       "(hou, date)"),
        ("idx_fact_publisher", "(publisher, date)"),
        ("idx_fact_cover",     cover),
    ]
    return [f"CREATE INDEX {n}{suffix} ON {table_name} {cols};" for n, cols in specs]


INDEX_BASE_NAMES = ["idx_fact_date", "idx_fact_canonical", "idx_fact_pod",
                    "idx_fact_hou", "idx_fact_publisher", "idx_fact_cover"]
