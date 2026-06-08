-- 005_fallback.sql
-- Adds per-tenant fallback message and suggested questions

ALTER TABLE tenant_settings
  ADD COLUMN IF NOT EXISTS fallback_message TEXT NOT NULL
    DEFAULT 'I''m sorry, I don''t have information about that. Try one of the suggested topics below.',
  ADD COLUMN IF NOT EXISTS suggested_questions TEXT[] NOT NULL DEFAULT '{}';
