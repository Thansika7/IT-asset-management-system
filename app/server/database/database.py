import os
import time
import logging
from dotenv import load_dotenv
from supabase import create_client, Client
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

DATABASE_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("SUPABASE_POSTGRES_URL")
if not DATABASE_URL:
    raise RuntimeError("Missing DATABASE_URL. Set SUPABASE_DB_URL (recommended) or SUPABASE_POSTGRES_URL.")

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()

SLOW_QUERY_MS = int(os.getenv("SLOW_QUERY_MS", "300"))


@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    started = getattr(context, "_query_start_time", None)
    if started is None:
        return
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms >= SLOW_QUERY_MS:
        logger.warning(
            "Slow query detected",
            extra={
                "userId": "system",
                "endpoint": "db",
                "method": "SQL",
                "statusCode": 200,
                "responseTime": int(elapsed_ms),
            },
        )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()