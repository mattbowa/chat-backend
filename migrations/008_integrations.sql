-- 008_integrations.sql
-- Generic integrations table for connecting external data sources (Shopify, WooCommerce, etc.)

CREATE TABLE integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'idle',
    last_synced_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, type)
);

CREATE INDEX idx_integrations_tenant ON integrations(tenant_id);

ALTER TABLE integrations ENABLE ROW LEVEL SECURITY;
