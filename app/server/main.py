import os
import uuid
import logging
import time
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware
from jose import JWTError, jwt
from sqlalchemy import text
from app.server.database.database import Base, engine, SessionLocal
from app.server.routes.auth import router as auth_router
from app.server.routes.employee import router as employee_router, me_router
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
from app.server.routes.audit import router as audit_router
from app.server.routes.branch import router as branch_router
from app.server.routes.asset_instances import router as asset_instances_router
from app.server.routes.health import router as health_router
from app.server.routes.finance import router as finance_router
from app.server.routes.notifications import router as notifications_router
from app.server.schema import asset, employee, category, attribute, request, tracking, audit
import app.server.schema.cmdb  # noqa: F401 — register CMDB tables
import app.server.schema.onboarding  # noqa: F401 — register onboarding preset tables
from app.server.schema.employee import Employee, EmployeeRole
from app.server.auth.service import ALGORITHM, SECRET_KEY, get_password_hash
from app.server.middlewares.cors import setup_cors
from app.server.exceptions.base import AppBaseException
from app.server.logging_utils import StructuredDefaultsFilter, StructuredJsonFormatter, IST

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
        # Flush immediately so every log entry lands on disk in real-time
        self.flush()


def configure_application_logging() -> None:
    """Route application logs to file and keep uvicorn console output."""
    file_handler = DailyFileHandler("logs")
    file_handler.setFormatter(StructuredJsonFormatter())
    file_handler.addFilter(StructuredDefaultsFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = []
    root_logger.addHandler(file_handler)

    # Keep uvicorn's own terminal handlers, and also persist uvicorn logs to file.
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.setLevel(logging.INFO)
        uvicorn_logger.addHandler(file_handler)


configure_application_logging()
logger = logging.getLogger(__name__)

app=FastAPI(title="Asset Control System")

# Setup CORS
setup_cors(app)
app.add_middleware(GZipMiddleware, minimum_size=500)


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


def _ensure_onboarding_preset_columns() -> None:
    """Backfill schema for environments created before onboarding presets were tenant-scoped."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'onboarding_presets'
                """
            )
        )
        existing = {row[0] for row in rows}

        if "organization_id" not in existing:
            conn.execute(text("ALTER TABLE onboarding_presets ADD COLUMN organization_id VARCHAR(50) NULL"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_onboarding_presets_organization_id ON onboarding_presets (organization_id)"))
            conn.execute(
                text(
                    """
                    ALTER TABLE onboarding_presets
                    ADD CONSTRAINT onboarding_presets_organization_id_fkey
                    FOREIGN KEY (organization_id)
                    REFERENCES organizations (organization_id)
                    ON DELETE CASCADE
                    """
                )
            )

        if "created_by" not in existing:
            conn.execute(text("ALTER TABLE onboarding_presets ADD COLUMN created_by VARCHAR(50) NULL"))


def _ensure_employee_permission_columns() -> None:
    """Backfill schema for JSON-only employee permissions in legacy databases."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'employee_permissions'
                """
            )
        )
        existing = {row[0] for row in rows}

        if "permissions_json" not in existing:
            conn.execute(text("ALTER TABLE employee_permissions ADD COLUMN permissions_json JSON NOT NULL DEFAULT '{}'::json"))


def _ensure_asset_instance_finance_columns() -> None:
    """Backfill schema for environments created before instance-level finance totals existed."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'asset_instances'
                """
            )
        )
        existing = {row[0] for row in rows}

        if "repair_cost_total" not in existing:
            conn.execute(text("ALTER TABLE asset_instances ADD COLUMN repair_cost_total FLOAT DEFAULT 0.0"))
        if "maintenance_cost_total" not in existing:
            conn.execute(text("ALTER TABLE asset_instances ADD COLUMN maintenance_cost_total FLOAT DEFAULT 0.0"))

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'assets'
                """
            )
        )
        existing_assets = {row[0] for row in rows}

        if "total_purchase_cost" not in existing_assets:
            conn.execute(text("ALTER TABLE assets ADD COLUMN total_purchase_cost FLOAT NOT NULL DEFAULT 0.0"))


def _ensure_performance_indexes() -> None:
    """Create missing performance indexes for common tenant/status/time filters."""
    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_assets_organization_id ON assets (organization_id)",
        "CREATE INDEX IF NOT EXISTS ix_assets_branch_id ON assets (branch_id)",
        "CREATE INDEX IF NOT EXISTS ix_assets_asset_id ON assets (asset_id)",
        "CREATE INDEX IF NOT EXISTS ix_assets_asset_status ON assets (asset_status)",
        "CREATE INDEX IF NOT EXISTS ix_assets_created_at ON assets (created_at)",
        "CREATE INDEX IF NOT EXISTS ix_asset_instances_organization_id ON asset_instances (organization_id)",
        "CREATE INDEX IF NOT EXISTS ix_asset_instances_branch_id ON asset_instances (branch_id)",
        "CREATE INDEX IF NOT EXISTS ix_asset_instances_asset_id ON asset_instances (asset_id)",
        "CREATE INDEX IF NOT EXISTS ix_asset_instances_instance_id ON asset_instances (instance_id)",
        "CREATE INDEX IF NOT EXISTS ix_asset_instances_status ON asset_instances (status)",
        "CREATE INDEX IF NOT EXISTS ix_asset_instances_created_at ON asset_instances (created_at)",
        "CREATE INDEX IF NOT EXISTS ix_tracking_organization_id ON tracking (organization_id)",
        "CREATE INDEX IF NOT EXISTS ix_tracking_branch_id ON tracking (branch_id)",
        "CREATE INDEX IF NOT EXISTS ix_tracking_asset_id ON tracking (asset_id)",
        "CREATE INDEX IF NOT EXISTS ix_tracking_instance_id ON tracking (instance_id)",
        "CREATE INDEX IF NOT EXISTS ix_tracking_assigned_date ON tracking (assigned_date)",
        "CREATE INDEX IF NOT EXISTS ix_requests_organization_id ON requests (organization_id)",
        "CREATE INDEX IF NOT EXISTS ix_requests_branch_id ON requests (branch_id)",
        "CREATE INDEX IF NOT EXISTS ix_requests_asset_id ON requests (asset_id)",
        "CREATE INDEX IF NOT EXISTS ix_requests_instance_id ON requests (instance_id)",
        "CREATE INDEX IF NOT EXISTS ix_requests_status ON requests (status)",
        "CREATE INDEX IF NOT EXISTS ix_requests_req_date ON requests (req_date)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_organization_id ON audit_logs (organization_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_branch_id ON audit_logs (branch_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_record_id ON audit_logs (record_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action)",
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_changed_at ON audit_logs (changed_at)",
        "CREATE INDEX IF NOT EXISTS ix_asset_lifecycle_organization_id ON asset_lifecycle (organization_id)",
        "CREATE INDEX IF NOT EXISTS ix_asset_lifecycle_asset_id ON asset_lifecycle (asset_id)",
        "CREATE INDEX IF NOT EXISTS ix_asset_lifecycle_instance_id ON asset_lifecycle (instance_id)",
        "CREATE INDEX IF NOT EXISTS ix_asset_lifecycle_event_type ON asset_lifecycle (event_type)",
        "CREATE INDEX IF NOT EXISTS ix_asset_lifecycle_timestamp ON asset_lifecycle (timestamp)",
    ]
    with engine.begin() as conn:
        for stmt in index_statements:
            conn.execute(text(stmt))


Base.metadata.create_all(bind=engine)
_ensure_organization_subscription_columns()
_ensure_request_branch_column()
_ensure_onboarding_preset_columns()
_ensure_employee_permission_columns()
_ensure_asset_instance_finance_columns()
_ensure_performance_indexes()

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

def _seed_categories():
    from app.server.schema.category import Category, AssetBehavior
    db = SessionLocal()
    try:
        # 1. Software Licenses
        lic_cat = db.query(Category).filter(Category.category_name == "Software Licenses").first()
        if not lic_cat:
            lic_cat = Category(
                category_name="Software Licenses",
                description="General software license assets tracked by key and expiry.",
                asset_behavior=AssetBehavior.LICENSE_BASED.value,
                organization_id=None # Global
            )
            db.add(lic_cat)
            logger.info("Seeded category: Software Licenses")

        # 2. Cloud Subscriptions
        sub_cat = db.query(Category).filter(Category.category_name == "Cloud Subscriptions").first()
        if not sub_cat:
            sub_cat = Category(
                category_name="Cloud Subscriptions",
                description="Subscription-based digital services (SaaS).",
                asset_behavior=AssetBehavior.SUBSCRIPTION_BASED.value,
                organization_id=None # Global
            )
            db.add(sub_cat)
            logger.info("Seeded category: Cloud Subscriptions")
        
        # 3. Hardware
        hw_cat = db.query(Category).filter(Category.category_name == "Hardware").first()
        if not hw_cat:
            hw_cat = Category(
                category_name="Hardware",
                description="Physical IT equipment and assets.",
                asset_behavior=AssetBehavior.INSTANCE_BASED.value,
                organization_id=None # Global
            )
            db.add(hw_cat)
            db.flush() # Ensure hw_cat has its ID for relationships
            logger.info("Seeded category: Hardware")

        from app.server.schema.category import SubCategory
        from app.server.schema.attribute import AssetAttribute

        # 4. Common Hardware Sub-categories
        sub_configs = [
            {"cat": "Hardware", "name": "Laptops", "attrs": ["RAM", "CPU", "Storage"]},
            {"cat": "Hardware", "name": "Desktops", "attrs": ["RAM", "CPU", "Storage"]},
            {"cat": "Hardware", "name": "Monitors", "attrs": ["Resolution", "Ports"]},
        ]

        # 5. Seed Interior Category
        int_cat = db.query(Category).filter(Category.category_name == "Interior").first()
        if not int_cat:
            int_cat = Category(
                category_name="Interior",
                description="Office furniture, cabins, and interior fixtures.",
                asset_behavior=AssetBehavior.INSTANCE_BASED.value,
                organization_id=None
            )
            db.add(int_cat)
            db.flush()
            logger.info("Seeded category: Interior")
        
        sub_configs.extend([
            {"cat": "Interior", "name": "Chairs", "attrs": ["Material", "Ergonomic"]},
            {"cat": "Interior", "name": "Tables", "attrs": ["Dimensions", "Material"]},
            {"cat": "Interior", "name": "Cabins", "attrs": ["Area", "Capacity"]},
        ])

        # 6. Seed Utilities Category
        ut_cat = db.query(Category).filter(Category.category_name == "Utilities").first()
        if not ut_cat:
            ut_cat = Category(
                category_name="Utilities",
                description="Facility utilities like HVAC, power systems, and fans.",
                asset_behavior=AssetBehavior.INSTANCE_BASED.value,
                organization_id=None
            )
            db.add(ut_cat)
            db.flush()
            logger.info("Seeded category: Utilities")

        sub_configs.extend([
            {"cat": "Utilities", "name": "AC Units", "attrs": ["BTU", "Energy Rating", "Inverter"]},
            {"cat": "Utilities", "name": "Fans", "attrs": ["Wattage", "Sweep Size", "Speed Settings"]},
            {"cat": "Utilities", "name": "UPS Systems", "attrs": ["KVA", "Backup Time"]},
            {"cat": "Utilities", "name": "Generators", "attrs": ["KVA", "Fuel Type"]},
        ])

        from app.server.schema.category import SubCategory
        from app.server.schema.attribute import AssetAttribute

        for config in sub_configs:
            # Find the parent category ID
            parent_cat = db.query(Category).filter(Category.category_name == config["cat"]).first()
            if not parent_cat: continue

            sub = db.query(SubCategory).filter(
                SubCategory.category_id == parent_cat.category_id,
                SubCategory.sub_category_name == config["name"]
            ).first()
            if not sub:
                sub = SubCategory(
                    category_id=parent_cat.category_id,
                    sub_category_name=config["name"],
                    description=f"Standard {config['name']} details.",
                    organization_id=None
                )
                db.add(sub)
                db.flush()
                logger.info(f"Seeded sub-category: {config['name']}")

                for attr_name in config["attrs"]:
                    attr = db.query(AssetAttribute).filter(
                        AssetAttribute.sub_category_id == sub.sub_category_id,
                        AssetAttribute.attribute_name == attr_name
                    ).first()
                    if not attr:
                        db.add(AssetAttribute(
                            sub_category_id=sub.sub_category_id,
                            attribute_name=attr_name,
                            data_type="String",
                            is_required=False,
                            organization_id=None
                        ))
        
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed categories: {e}")
    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    init_admin()
    _seed_categories()


def init_admin():
    db=SessionLocal()
    admin_email_env=os.getenv("ADMIN_EMAIL")
    admin_personal_env=os.getenv("ADMIN_PERSONAL_EMAIL")
    admin_password=os.getenv("ADMIN_PASSWORD") or str(uuid.uuid4())
    if admin_email_env:
        admin_email = admin_email_env.lower()
        admin_emp = db.query(Employee).filter(
            (Employee.email == admin_email) | (Employee.employee_id == "ADMIN-001")
        ).first()
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
app.include_router(me_router)
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
app.include_router(audit_router)
app.include_router(branch_router)
app.include_router(asset_instances_router)
app.include_router(health_router)
app.include_router(finance_router)
app.include_router(notifications_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}