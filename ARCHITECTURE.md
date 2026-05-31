# Chatyy — Architecture Document

## Product Summary

A multi-tenant SaaS platform where clients sign up, upload documents, customize their chatbot's behavior, and embed it for their end-users. All answers are grounded in the client's uploaded content via RAG (Retrieval-Augmented Generation).

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT BROWSER                           │
│                                                                 │
│   ┌─────────────────────┐     ┌──────────────────────────┐     │
│   │   Dashboard (Next)  │     │  Embeddable Chat Widget  │     │
│   │  - Upload docs      │     │  (iframe / JS snippet)   │     │
│   │  - Edit system prompt│     │  - End-user chat UI      │     │
│   │  - View analytics   │     └──────────────────────────┘     │
│   └─────────────────────┘                                       │
└────────────────────┬────────────────────────┬───────────────────┘
                     │ HTTPS                  │ HTTPS
┌────────────────────▼────────────────────────▼───────────────────┐
│                     FastAPI Backend                             │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ /auth    │  │ /docs    │  │ /chat     │  │ /settings    │  │
│  │ register │  │ upload   │  │ stream    │  │ system prompt│  │
│  │ login    │  │ list     │  │ history   │  │ model config │  │
│  │ JWT      │  │ delete   │  │           │  │              │  │
│  └──────────┘  └────┬─────┘  └─────┬─────┘  └──────────────┘  │
│                     │              │                            │
│              ┌──────▼──────┐  ┌────▼────────────────────┐      │
│              │  Ingestion  │  │    RAG Query Pipeline   │      │
│              │  Service    │  │                         │      │
│              │ parse→chunk │  │ embed query             │      │
│              │ →embed      │  │ → vector search (top-k) │      │
│              │ →store      │  │ → build prompt          │      │
│              └─────────────┘  │ → call Claude           │      │
│                               │ → stream response       │      │
│                               └─────────────────────────┘      │
└──────┬──────────────┬──────────────────────────────────────────┘
       │              │
┌──────▼──────┐ ┌─────▼──────────────────────────────────────────┐
│  Supabase   │ │              Supabase (pgvector)                │
│  Postgres   │ │                                                 │
│             │ │  vectors namespaced by tenant_id                │
│  tenants    │ │  + metadata: doc_id, chunk_index, source_page   │
│  users      │ └────────────────────────────────────────────────┘
│  documents  │
│  messages   │ ┌────────────────────────────────────────────────┐
│  settings   │ │              Supabase Storage                  │
└─────────────┘ │  raw uploaded files (PDF, DOCX, TXT, MD)       │
                └────────────────────────────────────────────────┘
```

---

## Data Model

### tenants
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| name | text | company/project name |
| slug | text unique | used in widget URL |
| plan | enum | free / pro / enterprise |
| created_at | timestamptz | |

### users
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| tenant_id | uuid FK | |
| email | text unique | |
| role | enum | owner / admin / member |
| hashed_password | text | |

### tenant_settings
| column | type | notes |
|---|---|---|
| tenant_id | uuid PK FK | |
| system_prompt | text | client-defined bot persona |
| model | text | default: claude-sonnet-4-6 |
| temperature | float | 0.0 – 1.0, default 0.3 |
| top_k_chunks | int | chunks retrieved per query, default 5 |
| max_response_tokens | int | default 1024 |
| allowed_topics | text[] | optional topic guardrails |

### documents
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| tenant_id | uuid FK | |
| filename | text | |
| storage_path | text | Supabase Storage key |
| status | enum | pending / processing / ready / error |
| chunk_count | int | |
| created_at | timestamptz | |

### messages
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| tenant_id | uuid FK | |
| session_id | uuid | groups a conversation |
| role | enum | user / assistant |
| content | text | |
| sources | jsonb | chunk refs used for this answer |
| created_at | timestamptz | |

---

## RAG Pipeline Detail

### Ingestion (on doc upload)
```
1. Save raw file → Supabase Storage
2. Parse text:
   - PDF   → pypdf2 / pdfplumber
   - DOCX  → python-docx
   - TXT/MD → direct read
3. Chunk: 512 tokens, 50-token overlap (LangChain RecursiveCharacterTextSplitter)
4. Embed each chunk: OpenAI text-embedding-3-small (1536-dim)
5. Upsert vectors into pgvector, metadata: {tenant_id, doc_id, chunk_index, text, page}
6. Update document status → "ready"
```

### Query (on chat message)
```
1. Embed user query (same model)
2. pgvector similarity search filtered by tenant_id, top_k=5
3. Build prompt:
   [system]  tenant.system_prompt + "Answer only using the context below."
   [context] chunk_1 \n chunk_2 \n ... chunk_5
   [user]    query
4. Stream response from Claude (claude-sonnet-4-6)
5. Save user message + assistant message + sources to DB
```

---

## API Surface

```
POST   /auth/register          create tenant + owner user
POST   /auth/login             returns JWT
GET    /auth/me                current user + tenant info

POST   /documents/upload       multipart, triggers ingestion job
GET    /documents              list tenant's docs + status
DELETE /documents/{id}         delete doc + its vectors

GET    /settings               get tenant_settings
PATCH  /settings               update system_prompt, temperature, etc.

POST   /chat                   send message, returns SSE stream
GET    /chat/sessions          list past conversation sessions
GET    /chat/sessions/{id}     get messages in a session

GET    /analytics/usage        message counts, doc counts, token usage
```

---

## Project Structure

```
chatyy/
├── ARCHITECTURE.md
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app entry point
│   │   ├── core/
│   │   │   ├── config.py        env-based settings (pydantic-settings)
│   │   │   ├── database.py      async SQLAlchemy + pgvector session
│   │   │   └── security.py      JWT encode/decode, password hashing
│   │   ├── models/              SQLAlchemy ORM models
│   │   ├── schemas/             Pydantic request/response schemas
│   │   ├── routers/             FastAPI route handlers
│   │   └── services/
│   │       ├── ingestion.py     parse → chunk → embed → store
│   │       ├── retrieval.py     embed query → pgvector search
│   │       └── llm.py           build prompt → call Claude → stream
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── (auth)/login/        sign in page
│   │   ├── (auth)/signup/       register page
│   │   ├── (dashboard)/
│   │   │   ├── documents/       upload + manage docs
│   │   │   ├── settings/        customize bot behavior
│   │   │   └── analytics/       usage stats
│   │   └── widget/[slug]/       public-facing chat UI (embeddable)
│   ├── components/
│   │   ├── chat/                ChatWindow, MessageBubble, InputBar
│   │   └── upload/              DropZone, DocList, StatusBadge
│   ├── lib/
│   │   └── api.ts               typed fetch wrappers for backend
│   └── package.json
└── .github/
    └── workflows/ci.yml
```

---

## Build Phases

### Phase 1 — Core (target: working end-to-end chat)
- [ ] Postgres schema + migrations (Alembic)
- [ ] Auth: register, login, JWT middleware
- [ ] Doc upload → ingestion pipeline
- [ ] Chat endpoint with RAG + streaming
- [ ] Basic Next.js dashboard: login, upload, chat preview

### Phase 2 — Customization
- [ ] System prompt editor with live preview
- [ ] Per-tenant model settings (temperature, top-k, max tokens)
- [ ] Source citations rendered in chat UI
- [ ] Embeddable widget (JS snippet + /widget/[slug] route)

### Phase 3 — Product
- [ ] Stripe billing (usage-based or seat-based)
- [ ] Usage analytics dashboard
- [ ] Doc processing queue (Celery or Supabase Edge Functions)
- [ ] Rate limiting per plan tier
- [ ] CI/CD (GitHub Actions → Railway or Render)

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Vector store | pgvector (Postgres extension) | Single DB, tenant isolation via SQL filter, no extra service |
| Embedding model | text-embedding-3-small | Cheap ($0.02/1M tokens), 1536-dim, strong quality |
| LLM | claude-sonnet-4-6 | Best instruction-following, 200k context window |
| Streaming | Server-Sent Events (SSE) | Simple, works without WebSocket infrastructure |
| Multi-tenancy | tenant_id column on all tables | Row-level isolation, easy to enforce via middleware |
| Background jobs | FastAPI BackgroundTasks (Phase 1) → Celery (Phase 3) | Simple now, scalable later |
