-- 006_fix_fallback_default.sql
-- Remove "Try one of the suggested topics below." from the fallback_message default

ALTER TABLE tenant_settings
  ALTER COLUMN fallback_message SET DEFAULT 'I''m sorry, I don''t have information about that.';

UPDATE tenant_settings
  SET fallback_message = 'I''m sorry, I don''t have information about that.'
  WHERE fallback_message = 'I''m sorry, I don''t have information about that. Try one of the suggested topics below.';
