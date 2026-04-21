import sys
from pathlib import Path

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.server.main import app as fastapi_app
from app.server.database.database import Base, get_db
from app.server.auth.service import get_current_user
from app.server.schema import Branch,Employee,EmployeeRole,Organization
from app.server.auth.service import get_password_hash, SECRET_KEY, ALGORITHM

SQLALCHEMY_DATABASE_URL="sqlite:///:memory:"
engine=create_engine(SQLALCHEMY_DATABASE_URL,connect_args={"check_same_thread": False},poolclass=StaticPool,)
TestingSessionLocal=sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db():
    connection=engine.connect()
    transaction=connection.begin()
    session=TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

@pytest.fixture(scope="function")
def client(db, org_admin):
    def override_get_db():
        try:
            yield db
        finally:
            pass
    def override_get_current_user():
        return org_admin
    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def default_org(db):
    org=Organization(
        organization_id="ORG-TEST-1",
        organization_name="Test Org 1",
        domain="test1.com"
    )
    db.add(org)
    db.commit()
    return org

@pytest.fixture(scope="function")
def default_branch(db, default_org):
    br=Branch(
        branch_id="BRN-TEST-1",
        organization_id=default_org.organization_id,
        branch_name="Headquarters"
    )
    db.add(br)
    db.commit()
    return br

@pytest.fixture(scope="function")
def org_admin(db, default_org, default_branch):
    admin=Employee(
        name="Org Admin",
        email="admin@test1.com",
        role=EmployeeRole.ORG_ADMIN,
        organization_id=default_org.organization_id,
        branch_id=default_branch.branch_id,
        password_hash=get_password_hash("Pass@123"),
        is_active=True
    )
    db.add(admin)
    db.commit()
    return admin

@pytest.fixture(scope="function")
def test_employee(db, default_org, default_branch):
    emp=Employee(
        name="Test Employee",
        email="emp@test1.com",
        role=EmployeeRole.EMPLOYEE,
        organization_id=default_org.organization_id,
        branch_id=default_branch.branch_id,
        password_hash=get_password_hash("Pass@123"),
        is_active=True
    )
    db.add(emp)
    db.commit()
    return emp

def create_token(email: str, role: str, org_id: str=None):
    expire=datetime.now(timezone.utc) + timedelta(minutes=30)
    payload={"sub": email, "role": role, "exp": expire}
    if org_id:
        payload["org_id"]=org_id
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

@pytest.fixture(scope="function")
def org_admin_token(org_admin):
    return create_token(org_admin.email, org_admin.role.value, org_admin.organization_id)

@pytest.fixture(scope="function")
def employee_token(test_employee):
    return create_token(test_employee.email, test_employee.role.value, test_employee.organization_id)
