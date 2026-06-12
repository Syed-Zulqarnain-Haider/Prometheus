"""Seed the local Postgres with sample fact data for a first run (no BigQuery).

Creates the sync-owned ``fact_daily_performance`` table (from the metric registry),
fills ~60 days of realistic sample rows across a few apps/pods/publishers/platforms,
refreshes ``dim_app``, and records a successful ``sync_runs`` row so the freshness
banner shows green. Run from the ``backend`` directory:

    PYTHONPATH=. python scripts/seed_local.py
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, date, datetime, timedelta

from app.core.database import AsyncSessionLocal, engine
from app.core.fact_table import FACT_TABLE, fact_metadata
from app.models import DimApp, SyncRun
from sqlalchemy import delete, insert, text

# canonical_key, name, publisher, pod, pod_owner, hou, platform
SAMPLE_APPS = [
    ("com.acme.nimbus", "Nimbus", "AcmeGames", "POD_ALPHA", "R. Okafor", "HOU_GAMES", "android"),
    ("apple.nimbus", "Nimbus", "AcmeGames", "POD_ALPHA", "R. Okafor", "HOU_GAMES", "ios"),
    ("com.acme.lumen", "Lumen", "AcmeGames", "POD_ALPHA", "R. Okafor", "HOU_GAMES", "android"),
    ("com.vega.pulse", "Pulse", "VegaHealth", "POD_BETA", "M. Haider", "HOU_HEALTH", "android"),
    ("apple.pulse", "Pulse", "VegaHealth", "POD_BETA", "M. Haider", "HOU_HEALTH", "ios"),
    ("com.vega.coin", "CoinKeeper", "VegaHealth", "POD_BETA", "M. Haider", "HOU_FINANCE", "ios"),
]

DAYS = 60


def _row(day: date, app: tuple[str, str, str, str, str, str, str]) -> dict[str, object]:
    key, name, publisher, pod, pod_owner, hou, platform = app
    base = random.uniform(0.6, 1.4)
    spend = round(random.uniform(2_000, 9_000) * base, 2)
    iap_net = round(random.uniform(3_000, 14_000) * base, 2)
    ad = round(random.uniform(800, 4_000) * base, 2)
    revenue = round(iap_net + ad, 2)
    paid_installs = int(random.uniform(400, 2_400) * base)
    organic = int(paid_installs * random.uniform(0.3, 1.1))
    total_installs = paid_installs + organic
    return {
        "date": day,
        "platform": platform,
        "canonical_key": key,
        "app_key": key,
        "app_name": name,
        "publisher": publisher,
        "developer": publisher,
        "pod": pod,
        "pod_owner": pod_owner,
        "hou": hou,
        "is_mapped": True,
        "store_total_installs": total_installs,
        "store_organic_installs": organic,
        "total_paid_installs": float(paid_installs),
        "total_ua_spend_usd": spend,
        "total_iap_gross_usd": round(iap_net * 1.3, 2),
        "total_iap_net_usd": iap_net,
        "total_ad_revenue_usd": ad,
        "admob_revenue_usd": round(ad * 0.6, 2),
        "applovin_revenue_usd": round(ad * 0.4, 2),
        "total_revenue_usd": revenue,
        "profit_usd": round(revenue - spend, 2),
    }


async def main() -> None:
    random.seed(42)
    async with engine.begin() as conn:
        await conn.run_sync(fact_metadata.create_all)  # idempotent

    today = date.today()
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM fact_daily_performance"))
        await session.execute(delete(DimApp))
        await session.execute(delete(SyncRun))

        for key, name, publisher, pod, pod_owner, hou, _platform in SAMPLE_APPS:
            await session.execute(
                insert(DimApp).values(
                    canonical_key=key,
                    app_name=name,
                    publisher=publisher,
                    pod=pod,
                    pod_owner=pod_owner,
                    hou=hou,
                    is_mapped=True,
                )
            )

        rows = 0
        for offset in range(DAYS):
            day = today - timedelta(days=offset)
            for app in SAMPLE_APPS:
                await session.execute(insert(FACT_TABLE).values(**_row(day, app)))
                rows += 1

        now = datetime.now(UTC)
        await session.execute(
            insert(SyncRun).values(
                started_at=now,
                finished_at=now,
                status="success",
                rows_loaded=rows,
                bq_built_at=now,
            )
        )
        await session.commit()
        print(f"Seeded {rows} fact rows across {len(SAMPLE_APPS)} apps and {DAYS} days.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
