"""Registry of admin-editable OPERATIONAL settings.

This is the single source of truth for which settings exist, their type, default,
bounds, and human labels. ONLY non-secret operational toggles belong here — there is
deliberately no mechanism to store a credential, connection string, key, or password.
Values are constrained to int/bool, so a secret string can never be persisted.

To add a setting: add a ``SettingSpec`` here (and read it where the backend needs it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

SettingType = Literal["int", "bool"]


@dataclass(frozen=True)
class SettingSpec:
    key: str
    type: SettingType
    default: int | bool
    label: str
    description: str
    minimum: int | None = None
    maximum: int | None = None


SETTINGS_REGISTRY: dict[str, SettingSpec] = {
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
}

# Settings the (non-admin) frontend is allowed to read so it can react to them.
# Operational only — never secret.
CLIENT_SETTING_KEYS: tuple[str, ...] = ("data_freshness_threshold_hours", "show_demo_widgets")


def coerce_value(spec: SettingSpec, value: Any) -> int | bool:
    """Validate + type a setting value. Rejects anything that isn't the declared
    int/bool (so a credential string can never be stored) and enforces bounds."""
    if spec.type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{spec.key} must be a boolean")
        return value
    # int — note bool is a subclass of int, so reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{spec.key} must be an integer")
    if spec.minimum is not None and value < spec.minimum:
        raise ValueError(f"{spec.key} must be >= {spec.minimum}")
    if spec.maximum is not None and value > spec.maximum:
        raise ValueError(f"{spec.key} must be <= {spec.maximum}")
    return value
