import asyncio
import os
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db, AsyncSessionLocal
from routers import public, admin, auth, internal, user_notifications
from routers.internal import prune_count_history_by_retention
from routers.public import close_vision_client, warm_preview_cache
from notification_worker import start_worker
from auth_admin import set_secret_key
from secret_config import (
    get_or_create_secret_key,
    ensure_internal_secret_file,
    get_internal_secret,
    get_internal_secret_file_path,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # SECRET_KEY: use env, or get/create from DB (auto-generated on first run; backup carries it)
    effective = os.getenv("SECRET_KEY", "").strip()
    if not effective:
        async with AsyncSessionLocal() as session:
            effective = await get_or_create_secret_key(session)
            await session.commit()
        set_secret_key(effective)
    else:
        set_secret_key(effective)
    # INTERNAL_SECRET: if unset and INTERNAL_SECRET_FILE set, create file; fail startup if we still have no secret
    ensure_internal_secret_file()
    if get_internal_secret_file_path() and not get_internal_secret():
        raise RuntimeError(
            "INTERNAL_SECRET_FILE is set but secret could not be read. Fix file path or set INTERNAL_SECRET."
        )
    task = start_worker()

    # Prune count_history on startup (older than retention_days)
    try:
        async with AsyncSessionLocal() as session:
            await prune_count_history_by_retention(session)
            await session.commit()
    except Exception:
        pass

    async def _prune_history_daily() -> None:
        while True:
            await asyncio.sleep(24 * 3600)  # 1 day
            try:
                async with AsyncSessionLocal() as session:
                    await prune_count_history_by_retention(session)
                    await session.commit()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    prune_task = asyncio.create_task(_prune_history_daily())

    async def _warm_preview_after_startup() -> None:
        await asyncio.sleep(5)
        try:
            await warm_preview_cache()
        except Exception:
            pass

    asyncio.create_task(_warm_preview_after_startup())
    yield
    await close_vision_client()
    prune_task.cancel()
    try:
        await prune_task
    except asyncio.CancelledError:
        pass
    if task is not None and not task.done():
        task.cancel()


app = FastAPI(
    title="KiteScope API",
    description="Real-time kite monitoring: when2fly, where2fly.",
    version="0.1.0",
    lifespan=lifespan,
)

# Security headers (X-Frame-Options, X-Content-Type-Options, etc.)
_USE_HSTS = os.getenv("SECURITY_HEADERS_HSTS", "").strip().lower() in ("1", "true", "yes")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if _USE_HSTS:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CORS: set CORS_ORIGINS (comma-separated) or PUBLIC_APP_URL for a single origin (e.g. Cloudflare Tunnel URL).
# Unset => allow_origins=["*"] for backward compatibility.
_cors_origins_raw = os.getenv("CORS_ORIGINS") or os.getenv("PUBLIC_APP_URL") or ""
_cors_origins = [s.strip().rstrip("/") for s in _cors_origins_raw.split(",") if s.strip()]
# Expose X-Detection-Count so frontend can read it from preview responses (CORS).
_cors_expose_headers = ["X-Detection-Count"]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=_cors_expose_headers,
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=_cors_expose_headers,
    )

app.include_router(public.router, prefix="/api", tags=["public"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(user_notifications.router, prefix="/api", tags=["user"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(internal.router, prefix="/api/internal", tags=["internal"])


@app.get("/")
async def root():
    return {"service": "KiteScope API", "docs": "/docs"}
