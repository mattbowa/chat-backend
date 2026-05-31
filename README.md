# Chatyy

A multi-tenant SaaS platform where clients sign up, upload documents, customize their chatbot, and embed it for their end-users. All answers are grounded in uploaded content via RAG (Retrieval-Augmented Generation).

See `ARCHITECTURE.md` for the full system design.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Frontend | Next.js 15 + Tailwind CSS |
| Database | Supabase (Postgres + pgvector) |
| File storage | Supabase Storage |
| Embeddings | OpenAI text-embedding-3-small |
| LLM | Anthropic Claude (claude-sonnet-4-6) |
| Auth | JWT (via python-jose) |

---

## Prerequisites

- Python 3.12 (not 3.13 or 3.14 — pydantic-core won't compile on those yet)
- Node.js 18+
- A [Supabase](https://supabase.com) account
- An [Anthropic](https://console.anthropic.com) API key
- An [OpenAI](https://platform.openai.com) API key

---

## External Services Setup

### 1. Supabase

1. Create a new project at supabase.com
2. Save the **database password** you set during creation
3. Enable the **pgvector** extension: Database → Extensions → search "vector" → enable
4. Run the migration: SQL Editor → paste contents of `backend/migrations/001_initial.sql` → Run
5. Create a storage bucket: Storage → New bucket → name it `documents` → keep private
6. Grab your credentials from Settings → API Keys:
   - **Project URL** → `SUPABASE_URL` (format: `https://xxxx.supabase.co`)
   - **Secret key** (`sb_secret_...`) → `SUPABASE_SERVICE_KEY`

### 2. Anthropic

1. Sign up at console.anthropic.com
2. Create an API key → `ANTHROPIC_API_KEY`

### 3. OpenAI

1. Sign up at platform.openai.com
2. Create a new secret key (name it `chatyy`, permissions: All) → `OPENAI_API_KEY`
3. Add at least $5 in credits (free tier no longer available for new accounts)

---

## Backend Setup

```bash
cd backend

# Use Python 3.12 — 3.13/3.14 will fail to install pydantic-core
# Install it if needed: brew install python@3.12
python3.12 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

Copy and fill in the environment file:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Build your DATABASE_URL from your Supabase project ref and db password:
# postgresql+asyncpg://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
DATABASE_URL=postgresql+asyncpg://postgres:...

# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=...

ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=sb_secret_...

OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

ENVIRONMENT=development
```

Start the server:

```bash
uvicorn app.main:app --reload
```

Verify it's running:

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

Register your first tenant:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"tenant_name":"My Company","tenant_slug":"my-company","email":"you@example.com","password":"secret123"}'
# → {"access_token":"...","token_type":"bearer"}
```

> Every time you open a new terminal, run `source venv/bin/activate` before starting the server.

---

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000/signup](http://localhost:3000/signup) to create your first account.

---

## Project Structure

```
chatyy/
├── ARCHITECTURE.md          Full system design and data model
├── README.md
├── docker-compose.yml       Run everything with Docker
├── backend/
│   ├── app/
│   │   ├── main.py          FastAPI entry point
│   │   ├── core/            Config, database, JWT security
│   │   ├── models/          SQLAlchemy ORM models
│   │   ├── schemas/         Pydantic request/response schemas
│   │   ├── routers/         API route handlers (auth, docs, chat, settings)
│   │   └── services/        RAG pipeline (ingestion, retrieval, LLM)
│   ├── migrations/
│   │   └── 001_initial.sql  Postgres schema (run once in Supabase SQL editor)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/
    │   ├── (auth)/          Login + signup pages
    │   ├── (dashboard)/     Documents, settings, analytics
    │   └── widget/[slug]/   Public embeddable chat UI
    ├── components/chat/     ChatWindow with SSE streaming
    └── lib/                 API client + useChat hook
```

---

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create tenant + owner account |
| POST | `/auth/login` | Get JWT token |
| GET | `/auth/me` | Current user + tenant info |
| POST | `/documents/upload` | Upload a doc (triggers RAG ingestion) |
| GET | `/documents` | List tenant's documents |
| DELETE | `/documents/{id}` | Delete doc + its vectors |
| GET | `/settings` | Get bot configuration |
| PATCH | `/settings` | Update system prompt, temperature, etc. |
| POST | `/chat` | Send message, returns SSE stream |
| GET | `/chat/sessions` | List past conversations |
| GET | `/chat/sessions/{id}` | Get messages in a session |

---

## Supported File Types

| Format | Extension |
|---|---|
| PDF | `.pdf` |
| Word | `.docx` |
| Plain text | `.txt` |
| Markdown | `.md` |

Max file size: 20 MB

---

## Common Issues

**`pydantic-core` fails to build**
You're on Python 3.13 or 3.14. Use Python 3.12:
```bash
brew install python@3.12
rm -rf venv
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**`externally-managed-environment` error**
Don't install packages globally. Always activate the venv first:
```bash
source venv/bin/activate
```

**`Failed to connect to localhost port 8000`**
The backend server isn't running. Start it with:
```bash
source venv/bin/activate
uvicorn app.main:app --reload
```
