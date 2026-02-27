from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import public, admin, auth, internal, user_notifications
from notification_worker import start_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = start_worker()
    yield
    if task is not None and not task.done():
        task.cancel()


app = FastAPI(
    title="KiteScope API",
    description="Real-time kite monitoring: when2fly, where2fly.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(public.router, prefix="/api", tags=["public"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(user_notifications.router, prefix="/api", tags=["user"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(internal.router, prefix="/api/internal", tags=["internal"])


@app.get("/")
async def root():
    return {"service": "KiteScope API", "docs": "/docs"}
