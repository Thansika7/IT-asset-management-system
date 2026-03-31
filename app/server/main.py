import os
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.server.database.database import Base, engine, SessionLocal
from app.server.routes.auth import router as auth_router
from app.server.routes.employee import router as employee_router
from app.server.routes.stock import router as stock_router
from app.server.routes.request import router as req_router
from app.server.routes.account import router as account_router
from app.server.routes.tracking import router as tracking_router
from app.server.schema import asset, employee, category, attribute, request, tracking, audit
from app.server.schema.employee import Employee, EmployeeRole
from app.server.auth.service import get_password_hash
from app.server.middlewares.cors import setup_cors
from app.server.exceptions.base import AppBaseException

app=FastAPI(title="IT Asset Management System")

# Setup CORS
setup_cors(app)

Base.metadata.create_all(bind=engine)

@app.exception_handler(AppBaseException)
async def app_exception_handler(request: Request, exc: AppBaseException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.__class__.__name__, "message": exc.detail}
    )

@app.on_event("startup")
def init_admin():
    db=SessionLocal()
    admin_email_env=os.getenv("ADMIN_EMAIL")
    admin_password=os.getenv("ADMIN_PASSWORD") or str(uuid.uuid4())
    if admin_email_env:
        admin_email = admin_email_env.lower()
        admin_emp=db.query(Employee).filter(Employee.email==admin_email).first()
        if not admin_emp:
            admin_emp = Employee(
                employee_id="ADMIN-001",
                name="System Administrator",
                email=admin_email,
                role=EmployeeRole.ADMIN,
                password_hash=get_password_hash(admin_password),
                is_active=True
            )
            db.add(admin_emp)
            db.commit()
            print(f"\n DEFAULT ADMIN CREATED ")
            print(f"EMAIL: {admin_email}")
            print(f"PASSWORD: {admin_password}")
            
    db.close()


app.include_router(auth_router)
app.include_router(employee_router)
app.include_router(stock_router)
app.include_router(req_router)
app.include_router(account_router)
app.include_router(tracking_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}

