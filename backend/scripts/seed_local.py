"""Seed the local Postgres with sample fact data for a first run (no BigQuery).

Creates the sync-owned ``fact_daily_performance`` table (from the metric registry),
fills ~60 days of realistic sample rows across a few apps/pods/publishers/platforms —
populating store, per-network UA (spend/impressions/clicks/engagement), ad-network,
and IAP-breakdown columns so every dashboard page demos with sample data — refreshes
``dim_app``, and records a successful ``sync_runs`` row. Idempotent / re-runnable.

Re-seeding ONLY refreshes sample data. It never deletes, deactivates, or otherwise
touches provisioned ``users`` / ``user_roles`` / ``user_scopes`` — and as a safety
net it re-asserts ``is_active=true`` for any existing admin so a re-seed can never
lock the admin out (roles and scopes are left exactly as they are).

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

# Per CLAUDE.md the canonical_key LINKS a game's platforms: a multi-platform game
# shares ONE canonical_key across its Android + iOS rows (iOS rows carry apple_id,
# Android rows android_package). That makes the table/breakdown endpoints — which
# group by canonical_key and SUM additive measures — collapse each game into a
# single row spanning its platforms (Nimbus and Pulse below ship on both).
#
#   game:      (canonical_key, name, publisher, pod, pod_owner, hou)
#   platforms: list of (platform, apple_id, android_package)
_Game = tuple[str, str, str, str, str, str]
_Platform = tuple[str, int | None, str | None]
GAMES: list[tuple[_Game, list[_Platform]]] = [
    (
        ("com.acme.nimbus", "Nimbus", "AcmeGames", "POD_ALPHA", "R. Okafor", "HOU_GAMES"),
        [("android", None, "com.acme.nimbus"), ("ios", 1_500_000_001, None)],
    ),
    (
        ("com.acme.lumen", "Lumen", "AcmeGames", "POD_ALPHA", "R. Okafor", "HOU_GAMES"),
        [("android", None, "com.acme.lumen")],
    ),
    (
        ("com.vega.pulse", "Pulse", "VegaHealth", "POD_BETA", "M. Haider", "HOU_HEALTH"),
        [("android", None, "com.vega.pulse"), ("ios", 1_500_000_002, None)],
    ),
    (
        ("com.vega.coin", "CoinKeeper", "VegaHealth", "POD_BETA", "M. Haider", "HOU_FINANCE"),
        [("ios", 1_500_000_003, None)],
    ),
]

# Flattened to one entry per (game, platform) for the daily fact rows:
#   (canonical_key, name, publisher, pod, pod_owner, hou, platform, apple_id, android_package)
SAMPLE_APPS: list[tuple[str, str, str, str, str, str, str, int | None, str | None]] = [
    (*game, platform, apple_id, android_package)
    for game, platforms in GAMES
    for platform, apple_id, android_package in platforms
]

DAYS = 60


def _impr_clicks(installs: int) -> tuple[int, int]:
    impressions = int(installs * random.uniform(180, 360))
    clicks = int(impressions * random.uniform(0.012, 0.05))
    return impressions, clicks


def _row(
    day: date,
    app: tuple[str, str, str, str, str, str, str, int | None, str | None],
) -> dict[str, object]:
    key, name, publisher, pod, pod_owner, hou, platform, apple_id, android_package = app
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

    # Infra / tech cost: a few % of gross revenue (IAP gross + ad), so it visibly
    # reduces Gross Profit (= gross_revenue − UA spend − tech_cost) on the Overview.
    tech_cost = round((gross + ad) * random.uniform(0.03, 0.07), 2)

    return {
        "date": day,
        "platform": platform,
        "canonical_key": key,
        "app_key": key,
        "apple_id": apple_id,
        "android_package": android_package,
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
        "tech_cost_usd": tech_cost,
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

        # One dim_app row per game (canonical_key is the PK), carrying BOTH platform
        # identifiers so a multi-platform game maps to its Android and iOS stores —
        # mirroring the linked-key model in production.
        for (key, name, publisher, pod, pod_owner, hou), platforms in GAMES:
            apple_id = next((a for _p, a, _pkg in platforms if a is not None), None)
            android_package = next((pkg for _p, _a, pkg in platforms if pkg is not None), None)
            await session.execute(
                insert(DimApp).values(
                    canonical_key=key,
                    app_name=name,
                    publisher=publisher,
                    pod=pod,
                    pod_owner=pod_owner,
                    hou=hou,
                    is_mapped=True,
                    apple_id=apple_id,
                    android_package=android_package,
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

        # Safety net: re-seeding sample data must never lock the admin out. We only
        # touched fact/dim/sync tables above (never users), but here we explicitly
        # re-assert is_active=true for every admin — preserving their role and scope
        # (we update ONLY the is_active flag, and only ever set it true). No-op when
        # there are no users yet (fresh DB). All SQL below is static (no user input).
        reactivated = await session.scalar(
            text(
                "SELECT count(*) FROM users u WHERE u.is_active = false AND EXISTS ("
                "  SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id"
                "  WHERE ur.user_id = u.id AND r.name = 'admin')"
            )
        )
        await session.execute(
            text(
                "UPDATE users SET is_active = true WHERE id IN ("
                "  SELECT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id"
                "  WHERE r.name = 'admin')"
            )
        )
        active_admins = await session.scalar(
            text(
                "SELECT count(*) FROM users u WHERE u.is_active = true AND EXISTS ("
                "  SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id"
                "  WHERE ur.user_id = u.id AND r.name = 'admin')"
            )
        )

        await session.commit()
        print(f"Seeded {rows} fact rows across {len(SAMPLE_APPS)} apps and {DAYS} days.")
        note = f" (re-activated {reactivated})" if reactivated else ""
        print(f"Preserved {active_admins} active admin user(s){note}; users untouched otherwise.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
