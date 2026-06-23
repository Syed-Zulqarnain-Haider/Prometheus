"""Drift guard for the sync vendored into the backend image.

The backend container vendors the daily sync (``backend/sync/``) so the sync job and
admin provisioning can run from one image on a single-VM deploy (see
``docs/DEPLOY-UBUNTU.md``). The canonical source is the repo-root ``sync/`` (shipped to
Cloud Run via ``sync/Dockerfile``). This test fails if the vendored copy ever drifts
from the canonical one — keeping a single source of truth for the sync + metric
registry.
"""

from pathlib import Path

_VENDORED = Path(__file__).resolve().parents[1] / "sync"  # backend/sync
_CANONICAL = Path(__file__).resolve().parents[2] / "sync"  # repo-root sync
_FILES = ("sync_job.py", "metric_registry.py", "requirements.txt")


def test_vendored_sync_is_byte_identical_to_canonical() -> None:
    for name in _FILES:
        vendored = (_VENDORED / name).read_bytes()
        canonical = (_CANONICAL / name).read_bytes()
        assert vendored == canonical, (
            f"backend/sync/{name} has drifted from the canonical sync/{name}; "
            f"re-copy it (cp sync/{name} backend/sync/{name})."
        )
