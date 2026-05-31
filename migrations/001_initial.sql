-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Enums
CREATE TYPE plan_enum AS ENUM ('free', 'pro', 'enterprise');
CREATE TYPE role_enum AS ENUM ('owner', 'admin', 'member');
CREATE TYPE doc_status_enum AS ENUM ('pending', 'processing', 'ready', 'error');
CREATE TYPE role_msg_enum AS ENUM ('user', 'assistant');

-- Tenants
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    plan plan_enum NOT NULL DEFAULT 'free',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tenants_slug ON tenants(slug);

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    role role_enum NOT NULL DEFAULT 'owner',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_tenant ON users(tenant_id);

-- Tenant settings
CREATE TABLE tenant_settings (
    tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    system_prompt TEXT NOT NULL DEFAULT 'You are a helpful assistant. Answer questions based only on the provided context.',
    model TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
    temperature FLOAT NOT NULL DEFAULT 0.3,
    top_k_chunks INT NOT NULL DEFAULT 5,
    max_response_tokens INT NOT NULL DEFAULT 1024
);

-- Documents
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    status doc_status_enum NOT NULL DEFAULT 'pending',
    chunk_count INT NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_documents_tenant ON documents(tenant_id);

-- Document chunks (vector store)
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536) NOT NULL
);
CREATE INDEX idx_chunks_tenant ON document_chunks(tenant_id);
-- IVFFlat index for ANN search (build after inserting >1000 vectors)
-- CREATE INDEX idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Messages
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    role role_msg_enum NOT NULL,
    content TEXT NOT NULL,
    sources JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_messages_tenant ON messages(tenant_id);
CREATE INDEX idx_messages_session ON messages(session_id);
