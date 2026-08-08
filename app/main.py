import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import analytics, auth, chat, contact, documents, integrations, public, settings

app = FastAPI(title="Chatyy API", version="0.1.0")

# In production, restrict to your frontend domain.
# The public /public/* endpoints must stay open for the embeddable widget.
ALLOWED_ORIGINS = (
    os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if os.getenv("ENVIRONMENT") == "production"
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(settings.router)
app.include_router(public.router)
app.include_router(analytics.router)
app.include_router(integrations.router)
app.include_router(contact.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
