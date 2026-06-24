"""Registry of admin-editable OPERATIONAL settings.

This is the single source of truth for which settings exist, their type, default,
bounds, group, and human labels. ONLY non-secret operational toggles belong here —
there is deliberately no mechanism to store a credential, connection string, key, or
password. Values are constrained to int/bool or a SHORT, FORMAT-VALIDATED string (an
HH:MM time, an IANA timezone, a GCP project id, or a fully-qualified BigQuery view) —
so a secret blob can never be persisted through this surface.

Settings are grouped: ``general`` (the System tab) and ``integration`` (the
Integration tab). The integration keys configure the BigQuery → Postgres sync's
NON-SECRET parameters (which project/view, whether/when it runs); the BigQuery
service-account key itself is NEVER stored here — it is a mounted file referenced only
by ``Settings.bq_credentials_path``.

To add a setting: add a ``SettingSpec`` here (and read it where the backend needs it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal
from zoneinfo import ZoneInfo

SettingType = Literal["int", "bool", "str"]
SettingGroup = Literal["general", "integration"]
StrFormat = Literal["hhmm", "iana_tz", "gcp_project", "bq_view"]

# Defensive hard cap on any stored string — a real value for every str format below is
# well under this; the cap exists so a key/JSON blob can never be pasted in.
_MAX_STR_LEN = 256

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# GCP project id: 6–30 chars, lowercase letter first, letters/digits/hyphens, no
# trailing hyphen. Empty is allowed too (means "not configured yet").
_GCP_PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
# Fully-qualified BigQuery view: 2 or 3 dot-separated segments (dataset.table or
# project.dataset.table); each segment is letters/digits/underscores/hyphens.
_BQ_VIEW_RE = re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+){1,2}$")


def _validate_str_format(fmt: StrFormat, key: str, value: str) -> None:
    """Raise ``ValueError`` if ``value`` is not a valid instance of ``fmt``."""
    if fmt == "hhmm" and not _HHMM_RE.match(value):
        raise ValueError(f"{key} must be a 24-hour time 'HH:MM' (e.g. 06:00)")
    if fmt == "iana_tz":
        try:
            ZoneInfo(value)
        except Exception as exc:  # noqa: BLE001 — any failure means "not a valid tz"
            raise ValueError(f"{key} must be a valid IANA timezone (e.g. UTC)") from exc
    # GCP project id is optional (empty == "not configured yet").
    if fmt == "gcp_project" and value != "" and not _GCP_PROJECT_RE.match(value):
        raise ValueError(f"{key} must be a valid GCP project id (or empty)")
    if fmt == "bq_view" and not _BQ_VIEW_RE.match(value):
        raise ValueError(
            f"{key} must be a fully-qualified BigQuery view "
            "(project.dataset.table or dataset.table)"
        )


@dataclass(frozen=True)
class SettingSpec:
    key: str
    type: SettingType
    default: int | bool | str
    label: str
    description: str
    group: SettingGroup = "general"
    minimum: int | None = None  # int bounds only
    maximum: int | None = None
    str_format: StrFormat | None = None  # str validation only


SETTINGS_REGISTRY: dict[str, SettingSpec] = {
    # ── General (System tab) ────────────────────────────────────────────────────
    "data_freshness_threshold_hours": SettingSpec(
        key="data_freshness_threshold_hours",
        type="int",
        default=48,
        label="Data freshness threshold (hours)",
        description="Data older than this many hours is flagged stale on the dashboard.",
        minimum=1,
        maximum=720,
    ),
    "show_demo_widgets": SettingSpec(
        key="show_demo_widgets",
        type="bool",
        default=True,
        label="Show demo widgets",
        description="Toggle the sample/demo widgets section on the dashboard.",
    ),
    # ── Integration (Integration tab) — NON-SECRET sync parameters only ──────────
    "gcp_project": SettingSpec(
        key="gcp_project",
        type="str",
        default="",
        label="GCP project",
        description="GCP project the BigQuery sync reads from. Leave empty to use the "
        "reader key's own project. Not a secret.",
        group="integration",
        str_format="gcp_project",
    ),
    "bq_view": SettingSpec(
        key="bq_view",
        type="str",
        default="terafort.api.daily_performance_v1",
        label="BigQuery view",
        description="Fully-qualified BigQuery view the sync reads (project.dataset.table). "
        "The app only ever reads this view, never the underlying table.",
        group="integration",
        str_format="bq_view",
    ),
    "sync_enabled": SettingSpec(
        key="sync_enabled",
        type="bool",
        default=False,
        label="Daily sync enabled",
        description="When on, the scheduler runs the BigQuery → Postgres sync once a day.",
        group="integration",
    ),
    "sync_schedule_time": SettingSpec(
        key="sync_schedule_time",
        type="str",
        default="06:00",
        label="Sync time (HH:MM)",
        description="Local clock time (in the sync timezone) the daily sync runs.",
        group="integration",
        str_format="hhmm",
    ),
    "sync_timezone": SettingSpec(
        key="sync_timezone",
        type="str",
        default="UTC",
        label="Sync timezone",
        description="IANA timezone the sync schedule time is interpreted in (e.g. UTC).",
        group="integration",
        str_format="iana_tz",
    ),
}

# Settings the (non-admin) frontend is allowed to read so it can react to them.
# Operational only — never secret. The integration keys are admin-only and are
# DELIBERATELY excluded here.
CLIENT_SETTING_KEYS: tuple[str, ...] = ("data_freshness_threshold_hours", "show_demo_widgets")


def coerce_value(spec: SettingSpec, value: Any) -> int | bool | str:
    """Validate + type a setting value. Rejects anything that isn't the declared
    int/bool/str (so a credential blob can never be stored), enforces int bounds, and
    enforces the declared string format."""
    if spec.type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{spec.key} must be a boolean")
        return value
    if spec.type == "str":
        if not isinstance(value, str):
            raise ValueError(f"{spec.key} must be a string")
        if len(value) > _MAX_STR_LEN:
            raise ValueError(f"{spec.key} is too long")
        if spec.str_format is not None:
            _validate_str_format(spec.str_format, spec.key, value)
        return value
    # int — note bool is a subclass of int, so reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{spec.key} must be an integer")
    if spec.minimum is not None and value < spec.minimum:
        raise ValueError(f"{spec.key} must be >= {spec.minimum}")
    if spec.maximum is not None and value > spec.maximum:
        raise ValueError(f"{spec.key} must be <= {spec.maximum}")
    return value
