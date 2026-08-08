-- 010_crawler_fallback_hardening.sql
-- 1. Track which messages were fallback ("I don't know") answers so the
--    dashboard can report unanswered questions. The flag is set on the USER
--    message that triggered the fallback, so reporting is a simple filter.
-- 2. Per-tenant domain allowlist for the public widget endpoint. Empty array
--    means "allow all" so existing tenants are unaffected.

-- Shopify integration removed from the app — drop any synced rows/documents.
-- (document_chunks rows cascade via documents FK.)
DELETE FROM documents WHERE storage_path LIKE 'shopify://%';
DELETE FROM integrations WHERE type = 'shopify';

ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS is_fallback BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE tenant_settings
  ADD COLUMN IF NOT EXISTS allowed_domains TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_messages_fallback
  ON messages (tenant_id, created_at)
  WHERE is_fallback;
