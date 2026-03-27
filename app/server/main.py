import os
import uuid
from fastapi import FastAPI

from app.server.database.database import Base, engine, SessionLocal
from app.server.routes import auth_router
from app.server.schema import asset, employee, category, attribute, request, tracking
from app.server.schema.employee import Employee, EmployeeRole
from app.server.auth.service import get_password_hash

app=FastAPI(title="IT Asset Management System")

Base.metadata.create_all(bind=engine)

def init_admin():
    db=SessionLocal()
    admin_email=os.getenv("ADMIN_EMAIL")
    admin_password=os.getenv("ADMIN_PASSWORD") or str(uuid.uuid4())
    
    if admin_email:
        existing=db.query(Employee).filter(Employee.email==admin_email).first()
        if not existing:
            admin_user=Employee(
                employee_id="ADMIN-001",
                name="System Administrator",
                email=admin_email,
                role=EmployeeRole.ADMIN,
                password_hash=get_password_hash(admin_password),
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            print(f"\n--- DEFAULT ADMIN CREATED ---")
            print(f"EMAIL: {admin_email}")
            print(f"PASSWORD: {admin_password}")
            print(f"-----------------------------\n")
    db.close()

init_admin()

app.include_router(auth_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
