import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL=os.getenv("SUPABASE_POSTGRES_URL") or os.getenv("DATABASE_URL", "sqlite:///./asset_management.db")

engine_options={"future": True, "pool_pre_ping": True}

if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"]={"check_same_thread": False}

engine=create_engine(DATABASE_URL, **engine_options)

SessionLocal=sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base=declarative_base()


def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()
