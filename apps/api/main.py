from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, chat, documents, health, ingest, workspaces

app = FastAPI(
    title="Sourcebook",
    description="Multi-tenant docuemnt AI workspace",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(documents.router)
app.include_router(ingest.router)
app.include_router(chat.router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.api_host, port=settings.api_port, reload=True)
