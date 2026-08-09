-- 011_qa_pairs.sql
-- Curated Q&A pairs: hand-written answers that live alongside document chunks
-- in retrieval. Powers the "Answer this" action on the unanswered-questions
-- report, so an unanswered question can be resolved without uploading a file.
--
-- The embedding is of the QUESTION only. Visitor queries are themselves
-- questions, so question-to-question similarity is what we want to match on;
-- the answer text is returned as content but never embedded.

CREATE TABLE qa_pairs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_qa_tenant ON qa_pairs(tenant_id);

-- Same posture as every other table: the backend uses SUPABASE_SERVICE_KEY
-- (which bypasses RLS), so this only blocks direct anon/public API access.
ALTER TABLE qa_pairs ENABLE ROW LEVEL SECURITY;

-- IVFFlat index for ANN search, mirroring the document_chunks note in
-- 001_initial.sql — build manually once a tenant has a lot of pairs.
-- CREATE INDEX idx_qa_embedding ON qa_pairs USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
