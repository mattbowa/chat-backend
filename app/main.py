from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import analytics, auth, chat, documents, public, settings

app = FastAPI(title="Chatyy API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allows widget to work on any website; lock this down in production
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


@app.get("/health")
async def health():
    return {"status": "ok"}
