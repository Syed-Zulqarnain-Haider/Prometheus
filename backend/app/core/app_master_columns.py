"""Single source of truth for the ``app_master`` table columns.

Mirrors the BigQuery table ``terafort.cross_platform.app_master_v2``. The ORM model, the
Pydantic schemas, the BigQuery sync (read) and the edit write-back (write) all derive their
column set, editability and BigQuery type mapping from HERE — never hand-list columns
elsewhere. A parity test asserts the ORM model matches this registry.

If a BigQuery column name is ever not identifier-safe (e.g. contains a space), give it a
sanitized Postgres ``name`` and its real BigQuery name via ``bq_name`` (back-quoted on
read/write). The current live table has no such columns.
"""

from __future__ import annotations

from dataclasses import dataclass

# canonical_key is the natural unique key (one row per app). Edits target exactly this row.
PRIMARY_KEY = "canonical_key"


@dataclass(frozen=True)
class AppMasterColumn:
    name: str  # Postgres / API column name
    pg_type: str  # logical type: text | bigint | boolean | double | timestamptz
    bq_name: str  # BigQuery column name (may contain spaces)
    bq_type: str  # BigQuery type for query params: STRING | INT64 | FLOAT64 | BOOL | TIMESTAMP
    editable: bool  # may an admin edit it (writes back to BigQuery)?


def _c(
    name: str, pg: str, bq: str, *, editable: bool = False, bq_name: str | None = None
) -> AppMasterColumn:
    return AppMasterColumn(
        name=name, pg_type=pg, bq_name=bq_name or name, bq_type=bq, editable=editable
    )


# Order mirrors the BigQuery schema. `editable=True` == the owner-approved curated set;
# identity/store fields and all pipeline-maintained (*_active / *_last_*_at / statuses /
# sync timestamps) stay read-only because upstream merge jobs overwrite them.
REGISTRY: list[AppMasterColumn] = [
    _c("app_name", "text", "STRING"),
    _c("platform", "text", "STRING"),
    _c("ios_bundle_id", "text", "STRING"),
    _c("android_package", "text", "STRING"),
    _c("sana_mirror_package", "text", "STRING"),
    _c("apple_account", "text", "STRING"),
    _c("google_play_account", "text", "STRING"),
    _c("facebook_app_id", "text", "STRING"),
    _c("type", "text", "STRING", editable=True),
    _c("publisher", "text", "STRING", editable=True),
    _c("developer", "text", "STRING", editable=True),
    _c("pod", "bigint", "INT64", editable=True),
    _c("pod_owner", "text", "STRING", editable=True),
    _c("hou", "text", "STRING", editable=True),
    _c("canonical_key", "text", "STRING"),  # PRIMARY KEY — never editable
    _c("app_type", "text", "STRING", editable=True),
    _c("apple_id", "bigint", "INT64"),
    _c("google_play_status", "text", "STRING"),
    _c("apple_status", "text", "STRING"),
    _c("added_by", "text", "STRING"),
    _c("first_added_to_master_at", "timestamptz", "TIMESTAMP"),
    _c("last_seen_in_source_at", "timestamptz", "TIMESTAMP"),
    _c("last_synced_at", "timestamptz", "TIMESTAMP"),
    _c("facebook_active", "boolean", "BOOL"),
    _c("facebook_last_spend_at", "timestamptz", "TIMESTAMP"),
    _c("google_ads_active", "boolean", "BOOL"),
    _c("google_ads_last_spend_at", "timestamptz", "TIMESTAMP"),
    _c("admob_active", "boolean", "BOOL"),
    _c("admob_last_revenue_at", "timestamptz", "TIMESTAMP"),
    _c("applovin_active", "boolean", "BOOL"),
    _c("applovin_last_revenue_at", "timestamptz", "TIMESTAMP"),
    _c("mintegral_pub_active", "boolean", "BOOL"),
    _c("mintegral_pub_last_revenue_at", "timestamptz", "TIMESTAMP"),
    _c("mintegral_adv_active", "boolean", "BOOL"),
    _c("mintegral_adv_last_spend_at", "timestamptz", "TIMESTAMP"),
    _c("apero_active", "boolean", "BOOL"),
    _c("apero_last_revenue_at", "timestamptz", "TIMESTAMP"),
    _c("needs_review", "boolean", "BOOL", editable=True),
    _c("review_reason", "text", "STRING", editable=True),
    _c("reviewed_at", "timestamptz", "TIMESTAMP"),
    _c("reviewed_by", "text", "STRING"),
    _c("revenue_share_pct", "double", "FLOAT64", editable=True),
    _c("cost_share_pct", "double", "FLOAT64", editable=True),
    _c("partner_name", "text", "STRING", editable=True),
    _c("partnership_terms", "text", "STRING", editable=True),
    _c("in_apple_console", "boolean", "BOOL", editable=True),
    _c("in_gp_console", "boolean", "BOOL", editable=True),
    _c("ops_notes", "text", "STRING", editable=True),
    # Newer app_master_v2 columns. net_revenue_share's BigQuery name has spaces/caps
    # ("Net Revenue Share") — carried via bq_name and back-quoted on read/write.
    _c("net_revenue_share", "double", "FLOAT64", editable=True, bq_name="Net Revenue Share"),
    _c("console_owned_by", "text", "STRING", editable=True),
]

BY_NAME: dict[str, AppMasterColumn] = {c.name: c for c in REGISTRY}
ALL_COLUMNS: list[str] = [c.name for c in REGISTRY]
EDITABLE_COLUMNS: list[str] = [c.name for c in REGISTRY if c.editable]
EDITABLE_SET: frozenset[str] = frozenset(EDITABLE_COLUMNS)
