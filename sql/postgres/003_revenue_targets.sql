-- 003_revenue_targets.sql — admin-set yearly + monthly revenue goals.
-- The Overview revenue-progress donut reads these (actual ÷ target); admins edit
-- them in the Admin panel. Yearly rows leave period_month NULL; monthly rows carry
-- 1–12. Two partial unique indexes enforce "one target per period" without letting
-- NULL months collide.

CREATE TABLE revenue_targets (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  period_type  TEXT NOT NULL CHECK (period_type IN ('year','month')),
  period_year  INTEGER NOT NULL,
  period_month INTEGER,
  target_usd   DOUBLE PRECISION NOT NULL CHECK (target_usd >= 0),
  set_by       UUID REFERENCES users(id),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT revenue_targets_month_valid CHECK (
       (period_type = 'year'  AND period_month IS NULL)
    OR (period_type = 'month' AND period_month BETWEEN 1 AND 12)
  )
);

CREATE UNIQUE INDEX uq_revenue_targets_year
  ON revenue_targets (period_year) WHERE period_type = 'year';
CREATE UNIQUE INDEX uq_revenue_targets_month
  ON revenue_targets (period_year, period_month) WHERE period_type = 'month';

GRANT SELECT, INSERT, UPDATE, DELETE ON revenue_targets TO api_service;
