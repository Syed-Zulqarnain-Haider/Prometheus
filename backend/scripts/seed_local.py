"""Seed the local Postgres with sample fact data for a first run (no BigQuery).

Creates the sync-owned ``fact_daily_performance`` table (from the metric registry),
fills ~60 days of realistic sample rows across a few apps/pods/publishers/platforms —
populating store, per-network UA (spend/impressions/clicks/engagement), ad-network,
and IAP-breakdown columns so every dashboard page demos with sample data — refreshes
``dim_app``, and records a successful ``sync_runs`` row. Idempotent / re-runnable.

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


def _impr_clicks(installs: int) -> tuple[int, int]:
    impressions = int(installs * random.uniform(180, 360))
    clicks = int(impressions * random.uniform(0.012, 0.05))
    return impressions, clicks


def _row(day: date, app: tuple[str, str, str, str, str, str, str]) -> dict[str, object]:
    key, name, publisher, pod, pod_owner, hou, platform = app
    base = random.uniform(0.6, 1.4)
    android = platform == "android"

    # ── UA spend split across networks (FB / Google / Mintegral) ─────────────
    total_spend = round(random.uniform(2_000, 9_000) * base, 2)
    fb_spend = round(total_spend * 0.50, 2)
    gads_spend = round(total_spend * 0.35, 2)
    mint_spend = round(total_spend - fb_spend - gads_spend, 2)

    fb_installs = int(fb_spend / random.uniform(1.5, 3.0))
    gads_installs = int(gads_spend / random.uniform(1.2, 2.5))
    mint_installs = int(mint_spend / random.uniform(0.8, 1.8))
    total_paid = fb_installs + gads_installs + mint_installs

    fb_impr, fb_clicks = _impr_clicks(fb_installs)
    gads_impr, gads_clicks = _impr_clicks(gads_installs)
    mint_impr, mint_clicks = _impr_clicks(mint_installs)

    fb_purchases = int(fb_installs * random.uniform(0.05, 0.2))
    fb_purchase_value = round(fb_purchases * random.uniform(2, 8), 2)
    gads_conversions = round(gads_installs * random.uniform(0.1, 0.4), 2)
    gads_conversions_value = round(gads_conversions * random.uniform(3, 9), 2)

    # ── Store installs ────────────────────────────────────────────────────────
    organic = int(random.uniform(150, 900) * base)
    total_store = total_paid + organic
    redownloads = int(total_store * random.uniform(0.10, 0.25))
    first_time = total_store - redownloads
    gp_uninstalls = int(total_store * random.uniform(0.05, 0.15)) if android else 0
    apple_restores = 0 if android else int(total_store * random.uniform(0.02, 0.08))

    # ── Ad revenue + impressions (eCPM = rev / impr * 1000) ──────────────────
    ad = round(random.uniform(800, 4_000) * base, 2)
    admob_rev = round(ad * 0.6, 2)
    applovin_rev = round(ad * 0.4, 2)
    admob_impr = int(admob_rev / random.uniform(8, 20) * 1000)
    applovin_impr = int(applovin_rev / random.uniform(6, 16) * 1000)

    # ── IAP breakdown: gross → refunds → fees → net (by platform) ────────────
    gross = round(random.uniform(4_000, 16_000) * base, 2)
    refunds = round(gross * random.uniform(0.02, 0.06), 2)
    fees = round((gross - refunds) * 0.30, 2)
    net = round(gross - refunds - fees, 2)

    revenue = round(net + ad, 2)

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
        # store
        "store_first_time_installs": first_time,
        "store_redownloads": redownloads,
        "store_total_installs": total_store,
        "store_organic_installs": organic,
        "gp_uninstalls": gp_uninstalls,
        "apple_restores": apple_restores,
        # paid UA installs
        "fb_paid_installs": fb_installs,
        "gads_paid_installs": float(gads_installs),
        "mint_adv_paid_installs": mint_installs,
        "total_paid_installs": float(total_paid),
        # UA spend + engagement
        "fb_spend_usd": fb_spend,
        "fb_impressions": fb_impr,
        "fb_clicks": fb_clicks,
        "fb_purchases": fb_purchases,
        "fb_purchase_value": fb_purchase_value,
        "gads_spend_usd": gads_spend,
        "gads_impressions": gads_impr,
        "gads_clicks": gads_clicks,
        "gads_conversions": gads_conversions,
        "gads_conversions_value": gads_conversions_value,
        "mint_adv_spend_usd": mint_spend,
        "mint_adv_impressions": mint_impr,
        "mint_adv_clicks": mint_clicks,
        "total_ua_spend_usd": round(fb_spend + gads_spend + mint_spend, 2),
        # ad revenue
        "admob_revenue_usd": admob_rev,
        "admob_impressions": admob_impr,
        "applovin_revenue_usd": applovin_rev,
        "applovin_impressions": applovin_impr,
        "total_ad_revenue_usd": ad,
        # IAP (per platform) + totals
        "gp_iap_gross_usd": gross if android else 0,
        "gp_iap_refunds_usd": refunds if android else 0,
        "gp_google_fee_usd": fees if android else 0,
        "gp_iap_net_usd": net if android else 0,
        "apple_iap_gross_usd": 0 if android else gross,
        "apple_iap_refunds_usd": 0 if android else refunds,
        "apple_fee_usd": 0 if android else fees,
        "apple_iap_net_usd": 0 if android else net,
        "apple_iap_purchases": 0 if android else fb_purchases,
        "total_iap_gross_usd": gross,
        "total_iap_net_usd": net,
        # headline
        "total_revenue_usd": revenue,
        "profit_usd": round(revenue - round(fb_spend + gads_spend + mint_spend, 2), 2),
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
