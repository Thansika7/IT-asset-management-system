import os
import uuid
import logging
import time
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from sqlalchemy import text
from app.server.database.database import Base, engine, SessionLocal
from app.server.routes.auth import router as auth_router
from app.server.routes.employee import router as employee_router
from app.server.routes.organization import router as org_router
from app.server.routes.stock import router as stock_router
from app.server.routes.assets import router as assets_router
from app.server.routes.analytics import router as analytics_router
from app.server.routes.request import router as req_router
from app.server.routes.account import router as account_router
from app.server.routes.tracking import router as tracking_router
from app.server.routes.discovery import router as discovery_router
from app.server.routes.cmdb import router as cmdb_router
from app.server.routes.onboarding_presets import router as onboarding_presets_router
from app.server.schema import asset, employee, category, attribute, request, tracking, audit
import app.server.schema.cmdb  # noqa: F401 — register CMDB tables
import app.server.schema.onboarding  # noqa: F401 — register onboarding preset tables
from app.server.schema.employee import Employee, EmployeeRole
from app.server.auth.service import ALGORITHM, SECRET_KEY, get_password_hash
from app.server.middlewares.cors import setup_cors
from app.server.exceptions.base import AppBaseException
from app.server.logging_utils import StructuredDefaultsFilter, StructuredJsonFormatter, IST

# --- Configure Daily Rotating Logs ---
class DailyFileHandler(logging.FileHandler):
    def __init__(self, directory="logs"):
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)
        filename = os.path.join(self.directory, f"{datetime.now(IST).strftime('%Y-%m-%d')}.log")
        super().__init__(filename)

    def emit(self, record):
        current_date_filename = os.path.join(self.directory, f"{datetime.now(IST).strftime('%Y-%m-%d')}.log")
        if self.baseFilename != os.path.abspath(current_date_filename):
            self.stream.close()
            self.baseFilename = os.path.abspath(current_date_filename)
            self.stream = self._open()
        super().emit(record)

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        DailyFileHandler("logs"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
for handler in logging.getLogger().handlers:
    handler.setFormatter(StructuredJsonFormatter())
    handler.addFilter(StructuredDefaultsFilter())

app=FastAPI(title="Asset Control System")

# Setup CORS
setup_cors(app)


def _ensure_organization_subscription_columns() -> None:
    """Backfill schema for environments created before subscription period fields existed."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'organizations'
                """
            )
        )
        existing = {row[0] for row in rows}

        if "subscription_start_at" not in existing:
            conn.execute(text("ALTER TABLE organizations ADD COLUMN subscription_start_at TIMESTAMPTZ NULL"))
        if "subscription_end_at" not in existing:
            conn.execute(text("ALTER TABLE organizations ADD COLUMN subscription_end_at TIMESTAMPTZ NULL"))


def _ensure_request_branch_column() -> None:
    """Backfill schema for environments created before requests were branch-scoped."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'requests'
                """
            )
        )
        existing = {row[0] for row in rows}

        if "branch_id" not in existing:
            conn.execute(text("ALTER TABLE requests ADD COLUMN branch_id VARCHAR(50) NULL"))


Base.metadata.create_all(bind=engine)
_ensure_organization_subscription_columns()
_ensure_request_branch_column()

@app.exception_handler(AppBaseException)
async def app_exception_handler(request: Request, exc: AppBaseException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.__class__.__name__, "message": exc.detail}
    )


def _extract_user_id(request: Request) -> str:
    token = request.headers.get("Authorization", "")
    if token.startswith("Bearer "):
        token = token[7:]
    elif request.cookies.get("access_token", "").startswith("Bearer "):
        token = request.cookies.get("access_token")[7:]
    else:
        token = request.cookies.get("access_token", "")

    if not token:
        return "anonymous"

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return "anonymous"

    email = str(payload.get("sub", "")).lower()
    if not email:
        return "anonymous"
    emp_id = payload.get("emp_id")
    if emp_id:
        return str(emp_id)
    return email


@app.middleware("http")
async def structured_request_logging(request: Request, call_next):
    start = time.perf_counter()
    user_id = _extract_user_id(request)

    try:
        response = await call_next(request)
    except Exception:
        response_time = int((time.perf_counter() - start) * 1000)
        logger.exception(
            "HTTP request failed",
            extra={
                "userId": user_id,
                "endpoint": request.url.path,
                "method": request.method,
                "statusCode": 500,
                "responseTime": response_time,
            },
        )
        raise

    response_time = int((time.perf_counter() - start) * 1000)
    message = "HTTP request completed"
    level = logging.INFO
    if response.status_code >= 500:
        message = "HTTP request failed"
        level = logging.ERROR
    elif response.status_code >= 400:
        message = "HTTP request completed with client error"
        level = logging.WARNING

    logger.log(
        level,
        message,
        extra={
            "userId": user_id,
            "endpoint": request.url.path,
            "method": request.method,
            "statusCode": response.status_code,
            "responseTime": response_time,
        },
    )
    return response

@app.on_event("startup")
def init_admin():
    db=SessionLocal()
    admin_email_env=os.getenv("ADMIN_EMAIL")
    admin_personal_env=os.getenv("ADMIN_PERSONAL_EMAIL")
    admin_password=os.getenv("ADMIN_PASSWORD") or str(uuid.uuid4())
    if admin_email_env:
        admin_email = admin_email_env.lower()
        admin_emp=db.query(Employee).filter(Employee.email==admin_email).first()
        if not admin_emp:
            admin_emp = Employee(
                employee_id="ADMIN-001",
                name="System Administrator",
                email=admin_email,
                personal_email=admin_personal_env,
                role=EmployeeRole.SUPER_ADMIN,
                password_hash=get_password_hash(admin_password),
                is_active=True
            )
            db.add(admin_emp)
            db.commit()
            logger.info(
                "Default admin created",
                extra={
                    "userId": admin_emp.employee_id,
                    "endpoint": "/startup",
                    "method": "SYSTEM",
                    "statusCode": 201,
                    "responseTime": 0,
                },
            )
            
    db.close()


app.include_router(auth_router)
app.include_router(employee_router)
app.include_router(org_router)
app.include_router(stock_router)
app.include_router(assets_router)
app.include_router(analytics_router)
app.include_router(req_router)
app.include_router(account_router)
app.include_router(tracking_router)
app.include_router(discovery_router)
app.include_router(cmdb_router)
app.include_router(onboarding_presets_router)
@app.get("/health")
def health_check():
    return {"status": "ok"}

