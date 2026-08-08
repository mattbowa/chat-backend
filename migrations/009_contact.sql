-- 009_contact.sql
-- Contact form submissions. Unauthenticated visitors (and tenants who hit the
-- monthly message limit) submit here instead of hitting a paid upgrade flow.

CREATE TABLE contact_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Set when the sender was a logged-in tenant hitting a limit; NULL for
    -- anonymous submissions from the public /contact page.
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    message TEXT NOT NULL,
    -- Free-text hint about where the form was submitted from, e.g.
    -- 'contact_page' or 'message_limit'.
    source TEXT NOT NULL DEFAULT 'contact_page',
    handled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_contact_submissions_created ON contact_submissions(created_at DESC);
CREATE INDEX idx_contact_submissions_tenant ON contact_submissions(tenant_id);

ALTER TABLE contact_submissions ENABLE ROW LEVEL SECURITY;
