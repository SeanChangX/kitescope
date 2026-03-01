# SQLite + SQLAlchemy async; single DB file in /app/data
import os
import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

_raw = os.getenv("DATABASE_URL", "sqlite:///./data/kitescope.db")
DATABASE_URL = _raw.replace("sqlite://", "sqlite+aiosqlite://", 1) if _raw.startswith("sqlite://") else _raw

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def _add_notification_columns(conn):
    """Add notification_subscriptions columns if missing (e.g. existing DB)."""
    result = conn.execute(text("PRAGMA table_info(notification_subscriptions)"))
    rows = result.fetchall()
    if not rows:
        return
    names = [r[1] for r in rows]
    if "last_notified_at" not in names:
        conn.execute(text("ALTER TABLE notification_subscriptions ADD COLUMN last_notified_at DATETIME"))
    if "release_threshold" not in names:
        conn.execute(text("ALTER TABLE notification_subscriptions ADD COLUMN release_threshold INTEGER"))
    if "released_at" not in names:
        conn.execute(text("ALTER TABLE notification_subscriptions ADD COLUMN released_at DATETIME"))


def _add_source_direct_embed(conn):
    """Add sources.direct_embed if missing (e.g. existing DB)."""
    result = conn.execute(text("PRAGMA table_info(sources)"))
    rows = result.fetchall()
    if not rows:
        return
    names = [r[1] for r in rows]
    if "direct_embed" not in names:
        conn.execute(text("ALTER TABLE sources ADD COLUMN direct_embed BOOLEAN DEFAULT 0"))


def _add_source_origin_url(conn):
    """Add sources.origin_url if missing (for go2rtc re-register)."""
    result = conn.execute(text("PRAGMA table_info(sources)"))
    rows = result.fetchall()
    if not rows:
        return
    names = [r[1] for r in rows]
    if "origin_url" not in names:
        conn.execute(text("ALTER TABLE sources ADD COLUMN origin_url VARCHAR(2048)"))


def _add_user_welcome_sent_at(conn):
    """Add users.welcome_sent_at if missing."""
    result = conn.execute(text("PRAGMA table_info(users)"))
    rows = result.fetchall()
    if not rows:
        return
    names = [r[1] for r in rows]
    if "welcome_sent_at" not in names:
        conn.execute(text("ALTER TABLE users ADD COLUMN welcome_sent_at DATETIME"))


def _migrate_users_autoincrement(conn):
    """Recreate users table with SQLite AUTOINCREMENT so deleted IDs are never reused."""
    if "sqlite" not in DATABASE_URL:
        return
    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'"))
    if not result.fetchone():
        return
    result = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"))
    row = result.fetchone()
    if not row:
        return
    create_sql = row[0]
    if "AUTOINCREMENT" in create_sql:
        return
    new_sql = re.sub(
        r"INTEGER PRIMARY KEY(?!\s+AUTOINCREMENT)",
        "INTEGER PRIMARY KEY AUTOINCREMENT",
        create_sql,
        count=1,
    )
    new_sql = new_sql.replace("CREATE TABLE users(", "CREATE TABLE users_new(", 1)
    new_sql = new_sql.replace('CREATE TABLE "users"(', 'CREATE TABLE "users_new"(', 1)
    conn.execute(text(new_sql))
    conn.execute(text("INSERT INTO users_new SELECT * FROM users"))
    conn.execute(text("DROP TABLE users"))
    conn.execute(text("ALTER TABLE users_new RENAME TO users"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_users_autoincrement)
        await conn.run_sync(_add_notification_columns)
        await conn.run_sync(_add_source_direct_embed)
        await conn.run_sync(_add_source_origin_url)
        await conn.run_sync(_add_user_welcome_sent_at)
