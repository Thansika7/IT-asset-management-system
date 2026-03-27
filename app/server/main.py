from fastapi import FastAPI

from app.server.database.database import Base, engine
from app.server.routes import auth_router
from app.server.schema import asset, employee, furniture, hardware, request, software, tracking

app=FastAPI(title="IT Asset Management System")

Base.metadata.create_all(bind=engine)

app.include_router(auth_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
