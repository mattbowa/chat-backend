-- Branding fields on tenant_settings
ALTER TABLE tenant_settings
  ADD COLUMN IF NOT EXISTS bot_name TEXT NOT NULL DEFAULT 'AI Assistant',
  ADD COLUMN IF NOT EXISTS primary_color TEXT NOT NULL DEFAULT '#2563eb',
  ADD COLUMN IF NOT EXISTS logo_url TEXT;

-- ============================================================
-- STRIPE (future) — uncomment when ready to add billing
-- ============================================================
-- ALTER TABLE tenants
--   ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
--   ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT,
--   ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'free';
--
-- CREATE TABLE usage_records (
--   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--   tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
--   period_start DATE NOT NULL,
--   message_count INT NOT NULL DEFAULT 0,
--   UNIQUE (tenant_id, period_start)
-- );
