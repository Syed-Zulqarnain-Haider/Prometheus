"""BigQuery access for the App Master feature.

Two operations, both against the ``table_id`` passed in (the admin-editable setting):
  * ``fetch_rows``  — READ every row (reader key) for the BQ -> Postgres sync.
  * ``push_update`` — WRITE one row's editable columns (writer key) via parameterized DML.

Design notes:
  * The BigQuery client library is imported LAZILY so a plain API/dev environment (no
    sync image) still imports this module — it just raises ``BigQueryUnavailable``.
  * Reader and writer are DISTINCT service-account keys (paths in settings); the writer
    needs BigQuery Data Editor and is required ONLY for edits.
  * Column names come from the single-source registry; any non-identifier-safe BigQuery
    name (via ``bq_name``) is back-quoted for BigQuery and aliased to its sanitized Postgres
    name on read.
  * These functions are BLOCKING (google-cloud-bigquery is sync); callers run them in a
    worker thread. They CANNOT be exercised without real GCP access.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.app_master_columns import BY_NAME, PRIMARY_KEY, REGISTRY
from app.core.config import Settings

log = logging.getLogger("app.services.app_master_bq")

# Both read and write must run query JOBS (a SELECT / an UPDATE both create a job), which the
# narrow ``bigquery.readonly`` scope forbids ("insufficient authentication scopes"). Use the
# full BigQuery scope — the same capability the daily sync and schema check run with.
_READ_SCOPES = ["https://www.googleapis.com/auth/bigquery"]
_WRITE_SCOPES = ["https://www.googleapis.com/auth/bigquery"]


class BigQueryUnavailable(RuntimeError):
    """The BigQuery client library isn't installed in this environment."""


class BigQueryNotConfigured(RuntimeError):
    """A required BigQuery key (reader or writer) is missing."""


class BigQueryWriteError(RuntimeError):
    """The write-back DML failed or did not affect exactly one row."""


class BigQueryReadError(RuntimeError):
    """The BigQuery read (sync) failed — e.g. wrong table name, column mismatch, or auth."""


def _bq_modules() -> tuple[Any, Any]:
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except Exception as exc:  # noqa: BLE001
        raise BigQueryUnavailable("BigQuery client library is not available.") from exc
    return bigquery, service_account


def _client(key_path: str, project: str | None, scopes: list[str]) -> Any:
    import os

    if not key_path or not os.path.exists(key_path):
        raise BigQueryNotConfigured("BigQuery service-account key is not mounted.")
    bigquery, service_account = _bq_modules()
    credentials = service_account.Credentials.from_service_account_file(key_path, scopes=scopes)
    return bigquery.Client(project=project or None, credentials=credentials)


def _bq_ident(name: str) -> str:
    """Back-quote a BigQuery column name (handles spaces / leading digits)."""
    return f"`{name.replace('`', '')}`"


def _query_project(table_id: str, settings: Settings) -> str | None:
    """The project the query JOB runs in. Prefer the table's own project (from a
    fully-qualified ``project.dataset.table``) so the job runs where the data lives — the
    same project the read-only schema check uses — falling back to the configured project."""
    parts = table_id.split(".")
    if len(parts) == 3 and parts[0]:
        return parts[0]
    return settings.bigquery_project or None


def _error_reason(exc: Exception) -> str:
    """First line of the provider error (admin-only diagnostic — names the missing
    permission / resource, e.g. table-access vs project jobs.create)."""
    raw = getattr(exc, "message", None) or str(exc)
    return raw.strip().split("\n")[0][:300]


def fetch_rows(settings: Settings, table_id: str) -> list[dict[str, Any]]:
    """Read ALL rows from the BigQuery App Master table, keyed by Postgres column names.

    ``table_id`` is the fully-qualified ``project.dataset.table`` (from the admin setting)."""
    client = _client(settings.bq_credentials_path, _query_project(table_id, settings), _READ_SCOPES)
    # Select each BQ column aliased to its sanitized Postgres name.
    select_list = ", ".join(f"{_bq_ident(c.bq_name)} AS {c.name}" for c in REGISTRY)
    table = _bq_ident_table(table_id)
    query = f"SELECT {select_list} FROM {table}"  # noqa: S608 — identifiers from the registry, not user input
    try:
        rows = client.query(query).result()
        return [{c.name: row[c.name] for c in REGISTRY} for row in rows]
    except Exception as exc:  # noqa: BLE001 — sanitize to first line; admin-only endpoint
        log.warning("App Master BigQuery read failed: %s", type(exc).__name__)
        raise BigQueryReadError(
            f"BigQuery read failed ({type(exc).__name__}): {_error_reason(exc)}"
        ) from exc


def _bq_ident_table(fq_table: str) -> str:
    """Back-quote a fully-qualified ``project.dataset.table`` for BigQuery."""
    return "`" + fq_table.replace("`", "") + "`"


def push_update(settings: Settings, table_id: str, key_value: str, changes: dict[str, Any]) -> None:
    """Apply ``changes`` (already validated to editable columns) to the single row whose
    primary key == ``key_value`` in ``table_id``, via a parameterized UPDATE. Raises if the
    writer key is missing or the statement doesn't affect exactly one row."""
    if not changes:
        return
    bigquery, _ = _bq_modules()
    client = _client(
        settings.bq_writer_credentials_path, _query_project(table_id, settings), _WRITE_SCOPES
    )

    set_fragments: list[str] = []
    params: list[Any] = []
    for name, value in changes.items():
        col = BY_NAME[name]
        param_name = f"p_{name}"
        set_fragments.append(f"{_bq_ident(col.bq_name)} = @{param_name}")
        params.append(bigquery.ScalarQueryParameter(param_name, col.bq_type, value))

    pk_col = BY_NAME[PRIMARY_KEY]
    params.append(bigquery.ScalarQueryParameter("pk", pk_col.bq_type, key_value))
    table = _bq_ident_table(table_id)
    query = (  # noqa: S608 — all identifiers come from the registry; values are bound params
        f"UPDATE {table} SET {', '.join(set_fragments)} WHERE {_bq_ident(pk_col.bq_name)} = @pk"
    )
    try:
        job = client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params))
        job.result()  # wait for completion / surface errors
    except Exception as exc:  # noqa: BLE001 — sanitize to first line; admin-only endpoint
        log.warning("App Master BigQuery write failed: %s", type(exc).__name__)
        raise BigQueryWriteError(
            f"BigQuery write failed ({type(exc).__name__}): {_error_reason(exc)}"
        ) from exc
    affected = job.num_dml_affected_rows
    if affected != 1:
        raise BigQueryWriteError(
            f"expected to update exactly 1 BigQuery row, updated {affected} "
            f"(key {key_value!r} may be missing or non-unique)."
        )
