from datetime import date, datetime, timedelta, timezone
import logging

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func as sql_func
from fastapi import HTTPException, status
from typing import List, Optional

from app.server.models.request import (
    RequestAssignNew,
    RequestCreate,
    RequestCrossBranchTransfer,
    RequestFormAssetOption,
    RequestFormOptions,
    RequestHRValidation,
    RequestReplace,
    RequestServiceComplete,
    RequestServiceStart,
    RequestManagerNotes,
    RequestResolve,
    RequestReview,
    RequestTriage,
    RequestFilterOptions,
)
from app.server.schema.request import Request, RequestStatus
from app.server.schema.asset import Asset, AssetStatus, AssetInstance, AssetUsageType
from app.server.schema.tracking import Tracking, MovementType, AllocationType, LifecycleEvent
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.organization import Branch, BranchStatus
from app.server.schema.category import Category
from app.server.services.email_service import EmailService
from app.server.services.stock_service import StockService
from app.server.services.account_service import AccountService
from app.server.services.audit_service import AuditService
from app.server.services.notification_service import NotificationPriority, NotificationService
from app.server.services.taxonomy import CANONICAL_CATEGORY_ORDER, canonical_category_name, canonical_subcategory_name, visible_category_names
from app.server.database.tenant import apply_tenant_filter

logger = logging.getLogger(__name__)


class RequestService:
    # FORM_CATEGORIES is being phased out in favor of dynamic DB categories.
    FORM_CATEGORIES = []
    FORM_REQUEST_TYPES = ["NEW", "SERVICE", "REPLACE", "RETURN", "TRANSFER"]
    FORM_ACTION_TYPES = ["NEW", "SERVICE", "REPLACE"]
    FORM_PRIORITIES = ["P1", "P2", "P3", "P4"]
    FORM_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    FORM_URGENCIES = ["LOW", "MEDIUM", "HIGH"]
    REASON_TEMPLATES = {
        "Laptop": [
            "Not powering on",
            "Battery issue",
            "Performance issue",
            "Damaged screen or body",
            "Need device for onboarding",
            "Other",
        ],
        "Monitor": [
            "Display not working",
            "Screen damaged",
            "Need monitor for workstation",
            "Other",
        ],
        "Keyboard": [
            "Keys not working",
            "Device physically damaged",
            "Need replacement keyboard",
            "Other",
        ],
        "Mouse": [
            "Pointer not working",
            "Buttons not working",
            "Need replacement mouse",
            "Other",
        ],
        "Printer": [
            "Printer not responding",
            "Print quality issue",
            "Need printer for team",
            "Other",
        ],
        "Phone": [
            "Not powering on",
            "Battery issue",
            "Call or network issue",
            "Need mobile device",
            "Other",
        ],
        "Accessory": [
            "Damaged accessory",
            "Need additional accessory",
            "Other",
        ],
        "Software": [
            "License access issue",
            "License expired or about to expire",
            "Need new software access",
            "Other",
        ],
        "Other": [
            "General issue",
            "Need review from support",
            "Other",
        ],
    }
    PRIORITY_ORDER = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}
    SLA_HOURS = {"P1": 1, "P2": 4, "P3": 24, "P4": 72}
    URGENCY_SLA_HOURS = {"HIGH": 1, "MEDIUM": 4, "LOW": 24}
    SEVERITY_DESCRIPTIONS = {
        "CRITICAL": "Complete system failure",
        "HIGH": "Major functionality affected",
        "MEDIUM": "Partial impact",
        "LOW": "Minor issue",
    }
    PRIORITY_DESCRIPTIONS = {
        "P1": "Immediate action required",
        "P2": "High urgency",
        "P3": "Normal",
        "P4": "Low",
    }
    PRIORITY_RESPONSE_TIME = {
        "P1": "< 1 hour",
        "P2": "< 4 hours",
        "P3": "< 24 hours",
        "P4": "2-3 days",
    }
    URGENCY_RESPONSE_TIME = {
        "HIGH": "< 1 hour",
        "MEDIUM": "< 4 hours",
        "LOW": "< 24 hours",
    }
    PRIORITY_MATRIX = {
        ("CRITICAL", "HIGH"): "P1",
        ("CRITICAL", "MEDIUM"): "P1",
        ("CRITICAL", "LOW"): "P2",
        ("HIGH", "HIGH"): "P1",
        ("HIGH", "MEDIUM"): "P2",
        ("HIGH", "LOW"): "P3",
        ("MEDIUM", "HIGH"): "P2",
        ("MEDIUM", "MEDIUM"): "P3",
        ("MEDIUM", "LOW"): "P4",
        ("LOW", "HIGH"): "P3",
        ("LOW", "MEDIUM"): "P4",
        ("LOW", "LOW"): "P4",
    }

    STATUS_ORDER = {
        "PENDING": 1,
        "PENDING_SUPPORT": 1,
        "PENDING_SUPPORT_TRIAGE": 1,
        "PENDING_MANAGER": 2,
        "HR_VERIFICATION": 1,
        "HELPDESK_TRIAGE": 2,
        "MANAGER_APPROVAL": 3,
        "ADMIN_APPROVAL": 4,
        "APPROVED_FOR_SUPPORT": 5,
        "READY": 5,
        "AWAITING_TRANSFER": 6,
        "WIP_SERVICE": 6,
        "IN_REPAIR": 6,
        "COMPLETED": 7,
        "REJECTED": 8,
    }

    @staticmethod
    def _urgency_sla_hours(urgency: str | None) -> int:
        return RequestService.URGENCY_SLA_HOURS.get((urgency or "MEDIUM").upper(), 4)

    @staticmethod
    def _get_escalation_role(req: Request) -> str | None:
        stage = (req.stage or "").upper()
        if stage == "HR_VERIFICATION":
            return "Manager"
        if stage in {"HELPDESK_TRIAGE", "READY", "IN_REPAIR"}:
            return "Manager"
        if stage == "MANAGER_APPROVAL":
            return "Admin"
        if stage == "ADMIN_APPROVAL":
            return "Admin"
        return None

    @staticmethod
    def _compute_escalation_state(req: Request):
        from datetime import datetime, timedelta, timezone

        req_date = req.req_date
        escalation_role = RequestService._get_escalation_role(req)
        if not req_date or not escalation_role:
            return False, None

        urgency = (req.urgency or "MEDIUM").upper()
        limit = req_date + timedelta(hours=RequestService._urgency_sla_hours(urgency))
        now = datetime.now(req_date.tzinfo) if req_date.tzinfo else datetime.now(timezone.utc).replace(tzinfo=None)
        if req.stage in {"COMPLETED", "REJECTED"}:
            return False, None
        return limit < now, escalation_role if limit < now else None

    @staticmethod
    def _serialize_request(req: Request):
        from app.server.models.request import RequestResponse
        from datetime import datetime, timedelta, timezone

        data = RequestResponse.model_validate(req)
        # Always populate requester info for the UI, even if the model doesn't expose it directly.
        if getattr(req, "employee", None):
            data.requester_name = getattr(req.employee, "name", None)
            data.requester_role = req.employee.role.value if getattr(req.employee, "role", None) else None
            data.requester_branch = req.employee.branch  # derived via relationship (branch_name)
        priority = (req.priority or "").strip().upper()
        req_date = req.req_date
        if req_date and priority:
            sla_target = req_date + timedelta(hours=RequestService.SLA_HOURS.get(priority, 24))
            data.sla_target_at = sla_target
            now = datetime.now(req_date.tzinfo) if req_date.tzinfo else datetime.now(timezone.utc).replace(tzinfo=None)
            data.sla_breached = req.stage not in {"COMPLETED", "REJECTED"} and sla_target < now
        severity = (req.severity or "").strip().upper()
        if severity:
            data.severity_description = RequestService.SEVERITY_DESCRIPTIONS.get(severity)
        if priority:
            data.priority_description = RequestService.PRIORITY_DESCRIPTIONS.get(priority)
            data.priority_response_time = RequestService.PRIORITY_RESPONSE_TIME.get(priority)
        urgency = (req.urgency or "").strip().upper()
        if urgency:
            data.urgency_response_time = RequestService.URGENCY_RESPONSE_TIME.get(urgency)
        data.escalation_triggered, data.escalation_role = RequestService._compute_escalation_state(req)
        return data

    @staticmethod
    def _bump_priority(priority: str) -> str:
        if priority == "P4":
            return "P3"
        if priority == "P3":
            return "P2"
        if priority == "P2":
            return "P1"
        return "P1"

    @staticmethod
    def _decrease_priority(priority: str) -> str:
        if priority == "P1":
            return "P2"
        if priority == "P2":
            return "P3"
        if priority == "P3":
            return "P4"
        return "P4"

    @staticmethod
    def _derive_priority(req: Request, severity: str, urgency: str, affected_users: int) -> str:
        priority = RequestService.PRIORITY_MATRIX.get((severity, urgency), "P3")

        category = (req.asset_category or "").strip().lower()
        requester_role = (req.employee.role.value if req.employee and req.employee.role else "").strip().lower()
        branch = ((req.employee.branch if req.employee else "") or "").strip().lower()
        issue_text = f"{req.asset_name or ''} {req.reason or ''}".lower()

        if "server" in category or "server" in issue_text:
            priority = RequestService._bump_priority(priority)
        elif "network" in category or "switch" in issue_text or "router" in issue_text:
            priority = RequestService._bump_priority(priority)
        elif any(term in category for term in ["mouse", "keyboard", "accessory"]):
            priority = RequestService._decrease_priority(priority)

        if requester_role in {"admin", "ceo"}:
            priority = RequestService._bump_priority(priority)

        if branch in {"hq", "headquarters"}:
            priority = RequestService._bump_priority(priority)

        if affected_users >= 10:
            priority = RequestService._bump_priority(priority)

        if "down" in issue_text and ("server" in issue_text or "production" in issue_text):
            priority = "P1"

        return priority

    @staticmethod
    def _derive_urgency(req: Request, severity: str, affected_users: int, requested_action: str) -> str:
        severity = (severity or "MEDIUM").upper()
        issue_text = f"{req.asset_name or ''} {req.reason or ''}".lower()
        category = (req.asset_category or "").strip().lower()
        action = (requested_action or "").strip().upper()

        if severity == "CRITICAL":
            return "HIGH"
        if affected_users >= 10:
            return "HIGH"
        if any(term in issue_text for term in ["production down", "not powering on", "not turning on", "network outage", "cannot login", "service disruption"]):
            return "HIGH"
        if any(term in category for term in ["server", "network", "security"]):
            return "HIGH"
        if action == "SERVICE" and severity == "HIGH":
            return "HIGH"
        if severity == "HIGH":
            return "MEDIUM"
        if action == "NEW" and any(term in issue_text for term in ["onboarding", "new joiner", "starter kit"]):
            return "MEDIUM"
        if any(term in category for term in ["mouse", "keyboard", "accessory"]):
            return "LOW"
        return "MEDIUM" if severity == "MEDIUM" else "LOW"

    @staticmethod
    def _status_rank(value: str | None) -> int:
        if not value:
            return 99
        raw = value.strip().upper()
        if raw in RequestService.STATUS_ORDER:
            return RequestService.STATUS_ORDER[raw]
        if raw.startswith("PENDING"):
            return 1
        if raw.startswith("APPROVED") or raw == "READY":
            return 5
        if raw.startswith("AWAITING") or raw.startswith("WIP") or raw.startswith("IN_"):
            return 6
        if raw == "COMPLETED":
            return 7
        if raw == "REJECTED":
            return 8
        return 50

    @staticmethod
    def validate_user_permission(user: Employee, allowed_roles: List[EmployeeRole], action: str) -> None:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {user.role} is not authorized to {action}.",
            )

    @staticmethod
    def validate_tenant_scope(request_obj: Request, user: Employee) -> None:
        if user.role == EmployeeRole.SUPER_ADMIN:
            return
        if request_obj.organization_id != user.organization_id:
            raise HTTPException(status_code=403, detail="Cross-organization access denied.")

    @staticmethod
    def validate_branch_scope(request_obj: Request, user: Employee) -> None:
        if user.role in {EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN}:
            return
        
        req_branch_id = (request_obj.employee.branch_id if request_obj.employee else request_obj.branch_id) or ""
        user_branch_id = user.branch_id or ""
        
        if req_branch_id and user_branch_id and req_branch_id != user_branch_id:
            # Check if this is a transfer targeting the user's branch
            user_branch_name = (user.branch or "").strip().upper()
            action_type = (request_obj.action_type or "").strip().upper()
            
            if action_type.startswith("TRANSFER:") and user_branch_name in action_type:
                return # Allow destination branch access for transfers
                
            raise HTTPException(status_code=403, detail="Cross-branch access denied.")

    @staticmethod
    def get_request_form_options(db: Session, current_user: Employee) -> RequestFormOptions:
        raw_category_names = [
            row[0]
            for row in apply_tenant_filter(
                db.query(Category.category_name),
                current_user,
                Category,
                allow_cross_branch=True,
            ).all()
            if row[0]
        ]
        visible_names = visible_category_names(raw_category_names)
        
        # Merge with any legacy FORM_CATEGORIES if still needed, but prioritize DB categories
        order_map = {name: index for index, name in enumerate(CANONICAL_CATEGORY_ORDER)}
        categories = sorted(set(visible_names), key=lambda name: (order_map.get(name, 999), name.lower()))
        
        # If no categories exist yet, fallback to canonical defaults to avoid empty dropdown
        if not categories:
            categories = CANONICAL_CATEGORY_ORDER[:]

        known_assets: list[RequestFormAssetOption] = []
        if current_user.role == EmployeeRole.EMPLOYEE:
            rows = (
                db.query(Tracking, Asset, Category, AssetInstance)
                .join(Asset, Tracking.asset_id == Asset.asset_id)
                .outerjoin(Category, Asset.category_id == Category.category_id)
                .outerjoin(AssetInstance, Tracking.instance_id == AssetInstance.instance_id)
                .filter(
                    Tracking.emp_id == current_user.employee_id,
                    Tracking.returned_at == None,
                )
                .all()
            )
            known_assets = [
                RequestFormAssetOption(
                    asset_id=asset.asset_id,
                    instance_id=tracking.instance_id,
                    serial_number=instance.serial_number if instance else None,
                    asset_name=asset.name,
                    category=canonical_category_name(category.category_name if category else None),
                    sub_category=canonical_subcategory_name(
                        category.category_name if category else None,
                        asset.sub_category.sub_category_name if asset.sub_category else None,
                    ),
                    branch=asset.branch,
                    owned_by_requester=True,
                )
                for tracking, asset, category, instance in rows
            ]
        else:
            query = apply_tenant_filter(db.query(Asset), current_user, Asset).options(joinedload(Asset.category), joinedload(Asset.sub_category))
            if current_user.role in [EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
                query = query.filter(Asset.branch_id == current_user.branch_id)
            # Managers can see assets from all branches
            known_assets = [
                RequestFormAssetOption(
                    asset_id=asset.asset_id,
                    instance_id=None,
                    serial_number=None,
                    asset_name=asset.name,
                    category=canonical_category_name(asset.category.category_name if asset.category else None),
                    sub_category=canonical_subcategory_name(
                        asset.category.category_name if asset.category else None,
                        asset.sub_category.sub_category_name if asset.sub_category else None,
                    ),
                    branch=asset.branch,
                    owned_by_requester=False,
                )
                for asset in query.order_by(Asset.name.asc()).limit(50).all()
            ]

        return RequestFormOptions(
            categories=categories,
            reasons_by_category=RequestService.REASON_TEMPLATES,
            known_assets=known_assets,
            request_types=RequestService.FORM_REQUEST_TYPES,
            priorities=RequestService.FORM_PRIORITIES,
            severities=RequestService.FORM_SEVERITIES,
            urgencies=RequestService.FORM_URGENCIES,
            action_types=RequestService.FORM_ACTION_TYPES,
        )

    @staticmethod
    def get_filter_options(db: Session, current_user: Employee) -> RequestFilterOptions:
        query = (
            apply_tenant_filter(db.query(Request), current_user, Request)
            .join(Request.employee, isouter=True)
            .join(Branch, Employee.branch_id == Branch.branch_id, isouter=True)
        )

        if current_user.role == EmployeeRole.EMPLOYEE:
            query = query.filter(Request.emp_id == current_user.employee_id)
        elif current_user.role in [EmployeeRole.SUPPORT_TEAM, EmployeeRole.HR, EmployeeRole.MANAGER] and current_user.branch_id:
            query = query.filter(Employee.branch_id == current_user.branch_id)

        rows = query.with_entities(Request.status, Request.request_type, Branch.branch_id, Branch.branch_name).all()
        statuses = sorted({(r[0] or "").strip() for r in rows if r[0]})
        request_types = sorted({(r[1] or "").strip().upper() for r in rows if r[1]})

        branches = []
        seen_branches = set()
        for r in rows:
            bid, bname = r[2], r[3]
            if bid and bid not in seen_branches:
                seen_branches.add(bid)
                branches.append({"id": bid, "name": bname or bid})
        
        branches.sort(key=lambda x: x["name"])

        if not request_types:
            request_types = RequestService.FORM_REQUEST_TYPES

        return RequestFilterOptions(
            statuses=statuses,
            request_types=request_types,
            priorities=RequestService.FORM_PRIORITIES,
            severities=RequestService.FORM_SEVERITIES,
            branches=branches,
        )

    @staticmethod
    def list_requests(
        db: Session,
        current_user: Employee,
        *,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        severity: Optional[str] = None,
        urgency: Optional[str] = None,
        branch: Optional[str] = None,
        sort_by_priority: bool = False,
        sort_by_status: bool = False,
        page: int = 1,
        per_page: int = 20,
        request_type: Optional[str] = None,
        search: Optional[str] = None,
    ):
        query = apply_tenant_filter(db.query(Request), current_user, Request).options(joinedload(Request.employee))
        
        if search:
            search_filter = f"%{search}%"
            query = query.join(Request.employee, isouter=True).join(Request.serviced_instance, isouter=True)
            
            query = query.filter(
                or_(
                    Request.request_id.ilike(search_filter),
                    Employee.name.ilike(search_filter),
                    Request.asset_name.ilike(search_filter),
                    Request.serial_number.ilike(search_filter),
                    AssetInstance.serial_number.ilike(search_filter),
                    Request.status.ilike(search_filter),
                    Request.priority.ilike(search_filter),
                    Request.severity.ilike(search_filter),
                    Request.request_type.ilike(search_filter),
                )
            )
        
        if current_user.role == EmployeeRole.SUPER_ADMIN:
            # Global admin: see everything.
            pass
        elif current_user.role == EmployeeRole.ORG_ADMIN:
            # Org admins already scoped by tenant filter (organization).
            pass
        elif current_user.role in [EmployeeRole.SUPPORT_TEAM, EmployeeRole.HR, EmployeeRole.MANAGER]:
            effective_branch_id = (current_user.branch_id or "").strip()
            effective_branch_name = (current_user.branch or "").strip()
            # Branch-scoped staff:
            # - If they have a branch_id, show requests from that branch.
            # - Also include transfers targeting their branch name (legacy action_type encoding).
            # - If they don't have a branch (HQ/central staff), rely on tenant filter and show all org requests.
            if effective_branch_id:
                conds = [Employee.branch_id == effective_branch_id]
                if effective_branch_name:
                    conds.append(Request.action_type.like(f"TRANSFER:{effective_branch_name}%"))
                query = query.join(Request.employee).filter(or_(*conds))
        else:
            # Regular employees: only their own tickets.
            query = query.filter(Request.emp_id == current_user.employee_id)

        if status:
            query = query.filter(Request.status == status.strip())
        if priority:
            query = query.filter(Request.priority == priority.strip().upper())
        if severity:
            query = query.filter(Request.severity == severity.strip().upper())
        if urgency:
            query = query.filter(Request.urgency == urgency.strip().upper())
        if request_type:
            query = query.filter(Request.request_type == request_type.strip().upper())
        if branch:
            # Accept either a branch_id (preferred) or a branch name.
            b = branch.strip()
            query = query.join(Request.employee)
            query = query.filter(or_(Employee.branch_id == b, Employee.branch_rel.has(Branch.branch_name == b)))

        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        offset = (page - 1) * per_page

        if sort_by_status:
            status_rank_expr = case(
                *[(func.upper(Request.status) == key, rank) for key, rank in RequestService.STATUS_ORDER.items()],
                else_=50,
            )
            query = query.order_by(status_rank_expr.asc())

        if sort_by_priority:
            priority_rank_expr = case(
                (func.upper(Request.priority) == "P1", 4),
                (func.upper(Request.priority) == "P2", 3),
                (func.upper(Request.priority) == "P3", 2),
                (func.upper(Request.priority) == "P4", 1),
                else_=0,
            )
            query = query.order_by(priority_rank_expr.desc())

        total = query.count()
        rows = query.order_by(Request.req_date.desc()).offset(offset).limit(per_page).all()

        return {
            "page": page,
            "per_page": per_page,
            "total": total,
            "items": [RequestService._serialize_request(req) for req in rows],
        }

    @staticmethod
    def get_inventory_across_branches(db: Session, category_name: str, current_user: Employee):
        from app.server.schema.category import Category

        query = apply_tenant_filter(db.query(
            Asset.branch,
            Asset.brand,
            Asset.name,
            func.sum(Asset.unused).label("available_quantity")
        ), current_user, Asset).join(Category).filter(
            Category.category_name == category_name,
            Asset.unused > 0
        )
        return query.group_by(Asset.branch, Asset.brand, Asset.name).all()

    @staticmethod
    def get_manager_email_for_branch(db: Session, branch: str, current_user: Employee) -> str | None:
        resolved_branch = RequestService._resolve_active_branch(db, branch, current_user)
        if resolved_branch:
            manager = apply_tenant_filter(db.query(Employee), current_user, Employee).join(
                Branch,
                Employee.branch_id == Branch.branch_id,
                isouter=True,
            ).filter(
                Employee.role == EmployeeRole.MANAGER,
                Employee.is_active == True,
                or_(
                    Employee.branch_id == resolved_branch.branch_id,
                    func.lower(Branch.branch_name) == resolved_branch.branch_name.strip().lower(),
                ),
            ).first()
        else:
            normalized = (branch or "").strip().lower()
            manager = apply_tenant_filter(db.query(Employee), current_user, Employee).join(
                Branch,
                Employee.branch_id == Branch.branch_id,
                isouter=True,
            ).filter(
                Employee.role == EmployeeRole.MANAGER,
                Employee.is_active == True,
                func.lower(Branch.branch_name) == normalized,
            ).first()
        return EmailService.delivery_email(manager) if manager else None

    @staticmethod
    def _resolve_active_branch(db: Session, branch: str, current_user: Employee) -> Branch | None:
        normalized = (branch or "").strip()
        if not normalized:
            return None
        branch_row = apply_tenant_filter(db.query(Branch), current_user, Branch).filter(
            Branch.status == BranchStatus.ACTIVE,
            or_(
                Branch.branch_id == normalized,
                func.lower(Branch.branch_name) == normalized.lower(),
            ),
        ).first()
        return branch_row

    @staticmethod
    def list_transfer_target_branches(db: Session, current_user: Employee) -> List[str]:
        branch_rows = apply_tenant_filter(db.query(Branch), current_user, Branch).filter(Branch.status == BranchStatus.ACTIVE).all()
        if not branch_rows:
            return []

        options: List[str] = []
        for branch in branch_rows:
            branch_name = (branch.branch_name or "").strip()
            if not branch_name:
                continue
            options.append(branch_name)

        return sorted(dict.fromkeys(options))

    @staticmethod
    def _higher_authority_roles_for_requester(requester_role: EmployeeRole) -> List[EmployeeRole]:
        if requester_role == EmployeeRole.EMPLOYEE:
            return [EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM, EmployeeRole.MANAGER]
        if requester_role == EmployeeRole.HR:
            return [EmployeeRole.SUPPORT_TEAM, EmployeeRole.MANAGER]
        if requester_role == EmployeeRole.MANAGER:
            return [EmployeeRole.SUPPORT_TEAM]
        if requester_role == EmployeeRole.SUPPORT_TEAM:
            return [EmployeeRole.MANAGER, EmployeeRole.HR]
        return [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]

    @staticmethod
    def _get_higher_authority_emails_for_request(
        db: Session,
        requester: Employee,
        current_user: Employee,
    ) -> List[str]:
        roles = RequestService._higher_authority_roles_for_requester(requester.role)
        branch_name = requester.branch or ""
        branch_recipients = RequestService.get_emails_by_roles_in_branch(db, roles, branch_name, current_user) if branch_name else []
        admin_emails = RequestService.get_admin_emails(db, current_user)
        requester_email = EmailService.delivery_email(requester)
        recipients = [mail for mail in [*branch_recipients, *admin_emails] if mail and mail != requester_email]
        return list(dict.fromkeys(recipients))

    @staticmethod
    def create_asset_request(db: Session, payload: RequestCreate, current_user: Employee):
        allowed_roles = [
            EmployeeRole.EMPLOYEE,
            EmployeeRole.MANAGER,
            EmployeeRole.HR,
            EmployeeRole.SUPER_ADMIN,
            EmployeeRole.SUPPORT_TEAM,
        ]
        RequestService.validate_user_permission(current_user, allowed_roles, "create requests")

        requester_email = EmailService.delivery_email(current_user)
        request_type = (payload.request_type.value if payload.request_type else None) or ("REPLACE" if payload.instance_id else "NEW")
        with db.begin():
            # Employee submits request in SUBMITTED state
            req = Request(
                emp_id=current_user.employee_id,
                organization_id=current_user.organization_id,
                branch_id=current_user.branch_id,
                asset_name=payload.asset_name,
                asset_category=payload.asset_category,
                reason=payload.reason,
                request_type=request_type,
                instance_id=payload.instance_id,
                serial_number=payload.serial_number,
                status=RequestStatus.SUBMITTED,
                sla_priority=payload.priority.value if payload.priority else "MEDIUM",
                severity=payload.severity.value if payload.severity else "MEDIUM",
                urgency=payload.urgency.value if payload.urgency else "MEDIUM",
            )
            db.add(req)
            db.flush()

            # Calculate SLA due date (24 hours for MEDIUM, 1 hour for HIGH, 72 for LOW, 4 for CRITICAL)
            from datetime import timedelta, timezone
            sla_hours = {"CRITICAL": 1, "HIGH": 4, "MEDIUM": 24, "LOW": 72}
            hours = sla_hours.get(req.sla_priority, 24)
            base_time = req.req_date or datetime.now(timezone.utc)
            req.sla_due = base_time + timedelta(hours=hours)

            AuditService.log_change(db, "requests", req.request_id, "CREATE", current_user, None, {
                "status": req.status,
                "asset_name": req.asset_name,
                "request_type": req.request_type,
            }, "REQUEST_SUBMISSION")

            try:
                NotificationService.emit(
                    db,
                    actor=current_user,
                    recipient_scope=current_user.employee_id,
                    event_type="REQUEST_CREATED",
                    title="Request Submitted",
                    message=f"Your request for {payload.asset_name} has been submitted.",
                    priority=NotificationPriority.MEDIUM,
                    dedup_key=f"request_created:{req.request_id}",
                    cooldown_hours=1,
                    metadata={"request_id": req.request_id, "asset_name": payload.asset_name},
                    email_to=requester_email,
                    email_subject=f"Request Submitted: {payload.asset_name}",
                    email_html=EmailService._wrap_email(
                        "Request Submitted",
                        payload.asset_name,
                        f"<p>Your request <strong>{req.request_id}</strong> has been submitted and is pending review.</p>",
                        accent_color="#0284c7",
                    ),
                )
            except Exception as exc:
                logger.warning("Request notification failed for request_id=%s: %s", req.request_id, str(exc))

        # Notify HR (non-transactional side effect)
        try:
            recipients = RequestService.get_emails_by_roles_in_branch(db, [EmployeeRole.HR], current_user.branch, current_user)
            EmailService.notify_branch_stakeholders(current_user.name, payload.asset_name, recipients, current_user.role, current_user.branch)
        except Exception as exc:
            logger.warning("Request stakeholder notification failed for request_id=%s: %s", req.request_id, str(exc))

        db.refresh(req)
        return RequestService._serialize_request(req)

    @staticmethod
    def validate_request_by_hr(db: Session, request_id: str, payload: RequestHRValidation, user: Employee):
        """HR validates request eligibility. SUBMITTED -> HR_VALIDATED or HR_REJECTED."""
        RequestService.validate_user_permission(user, [EmployeeRole.HR, EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN], "validate requests")

        with db.begin():
            # Lock for update (SELECT FOR UPDATE)
            req = apply_tenant_filter(db.query(Request), user, Request).filter(
                Request.request_id == request_id,
                Request.status == RequestStatus.SUBMITTED,
            ).with_for_update().first()

            if not req:
                raise HTTPException(status_code=404, detail="Request not found or not in SUBMITTED state")

            RequestService.validate_tenant_scope(req, user)
            RequestService.validate_branch_scope(req, user)

            old_status = req.status

            if payload.is_valid:
                req.status = RequestStatus.HR_VALIDATED
                req.hr_verified = True
                req.hr_validated_at = datetime.now(timezone.utc)
            else:
                req.status = RequestStatus.HR_REJECTED
                req.hr_verified = False
                req.rejected_at = datetime.now(timezone.utc)

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                user,
                {"status": old_status},
                {"status": req.status, "hr_verified": req.hr_verified},
                "HR_VALIDATION",
            )

            if not payload.is_valid:
                requester_email = EmailService.delivery_email(req.employee)
                NotificationService.emit(
                    db,
                    actor=user,
                    recipient_scope=req.emp_id,
                    event_type="REQUEST_REJECTED",
                    title="Request Rejected",
                    message=f"Request {req.request_id} was rejected during HR validation.",
                    priority=NotificationPriority.HIGH,
                    dedup_key=f"request_rejected:{req.request_id}",
                    cooldown_hours=1,
                    metadata={"request_id": req.request_id, "asset_name": req.asset_name},
                    email_to=requester_email,
                    email_subject=f"Request Rejected: {req.asset_name}",
                    email_html=EmailService._wrap_email(
                        "Request Rejected",
                        req.asset_name,
                        f"<p>Your request <strong>{req.request_id}</strong> was rejected during HR validation.</p>",
                        accent_color="#dc2626",
                    ),
                )

        db.refresh(req)
        if payload.is_valid:
            support_emails = RequestService.get_emails_by_roles_in_branch(db, [EmployeeRole.SUPPORT_TEAM], req.employee.branch, user)
            EmailService.notify_hr_verified(req.employee.name, req.asset_name, True, support_emails)
        else:
            # Notify employee
            requester_email = EmailService.delivery_email(req.employee)
            if requester_email:
                EmailService.notify_branch_stakeholders(user.name, f"Request {request_id} rejected", [requester_email], user.role, user.branch)
        
        return RequestService._serialize_request(req)

    @staticmethod
    def triage_asset_request(db: Session, request_id: str, payload: RequestTriage, user: Employee):
        """Support triages request. HR_VALIDATED -> TRIAGED. Reserves instance with SELECT FOR UPDATE."""
        with db.begin():
            # Lock for update (concurrency control)
            req = apply_tenant_filter(db.query(Request), user, Request).filter(
                Request.request_id == request_id,
                Request.status == RequestStatus.HR_VALIDATED,
            ).with_for_update().first()

            if not req:
                raise HTTPException(status_code=404, detail="Request not found or not in HR_VALIDATED state")

            if user.role not in {EmployeeRole.SUPPORT_TEAM, EmployeeRole.SUPER_ADMIN}:
                raise HTTPException(status_code=403, detail="Only Support Team may triage requests.")

            RequestService.validate_tenant_scope(req, user)
            RequestService.validate_branch_scope(req, user)

            # Validate instance if required
            resolved_instance_id = payload.instance_id or req.instance_id
            instance = None

            if payload.request_type.value.upper() in {"SERVICE", "REPLACE", "TRANSFER"}:
                if not resolved_instance_id and not payload.serial_number and not req.serial_number:
                    raise HTTPException(status_code=400, detail=f"instance_id or serial_number required for {payload.request_type.value}")

                # Lock instance (SELECT FOR UPDATE)
                if resolved_instance_id:
                    instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(
                        AssetInstance.instance_id == resolved_instance_id
                    ).with_for_update().first()
                elif payload.serial_number or req.serial_number:
                    serial_lookup = (payload.serial_number or req.serial_number or "").strip()
                    instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(
                        AssetInstance.serial_number == serial_lookup
                    ).with_for_update().first()

                if not instance:
                    raise HTTPException(status_code=404, detail="Asset instance not found")

                # Reserve instance
                instance.status = "RESERVED"
                req.instance_id = instance.instance_id
                req.serial_number = instance.serial_number

            # Update request to TRIAGED state
            req.status = RequestStatus.TRIAGED
            req.request_type = payload.request_type.value
            req.priority = payload.priority.value
            req.severity = payload.severity.value
            req.triaged_at = datetime.now(timezone.utc)

            # Lock request for next stage
            req.request_locked = True
            req.locked_at = datetime.now(timezone.utc)
            req.locked_by = user.employee_id

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                user,
                {"status": "HR_VALIDATED"},
                {"status": req.status, "request_type": req.request_type},
                "SUPPORT_TRIAGE",
            )

        db.refresh(req)

        # Notify manager
        manager_email = RequestService.get_manager_email_for_branch(db, req.employee.branch or "", user)
        if manager_email:
            EmailService.notify_stock_info_to_manager(req.employee.name, req.asset_name, manager_email, "Request triaged")

        return RequestService._serialize_request(req)


    @staticmethod
    def review_request_by_manager(db: Session, request_id: str, payload: RequestReview, user: Employee):
        """Manager approves/rejects triaged request. TRIAGED -> APPROVED or REJECTED."""
        RequestService.validate_user_permission(user, [EmployeeRole.MANAGER, EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN], "review requests")

        requester_email = None
        with db.begin():
            # Lock request with SELECT FOR UPDATE
            req = apply_tenant_filter(db.query(Request), user, Request).filter(
                Request.request_id == request_id,
                Request.status == RequestStatus.TRIAGED,
            ).with_for_update().first()

            if not req:
                raise HTTPException(status_code=404, detail="Request not found or not in TRIAGED state")

            RequestService.validate_tenant_scope(req, user)
            RequestService.validate_branch_scope(req, user)

            old_status = req.status

            if payload.is_approved:
                req.status = RequestStatus.APPROVED
                req.approved_at = datetime.now(timezone.utc)
            else:
                # ROLLBACK: Release reserved instance
                if req.instance_id:
                    instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(
                        AssetInstance.instance_id == req.instance_id
                    ).with_for_update().first()

                    if instance:
                        instance.status = "AVAILABLE"

                req.status = RequestStatus.REJECTED
                req.rejected_at = datetime.now(timezone.utc)

            req.request_locked = False

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                user,
                {"status": old_status},
                {"status": req.status},
                "MANAGER_APPROVAL",
            )

            requester_email = EmailService.delivery_email(req.employee)
            NotificationService.emit(
                db,
                actor=user,
                recipient_scope=req.emp_id,
                event_type="REQUEST_APPROVED" if payload.is_approved else "REQUEST_REJECTED",
                title="Request Approved" if payload.is_approved else "Request Rejected",
                message=(
                    f"Request {req.request_id} for {req.asset_name} was approved by manager."
                    if payload.is_approved
                    else f"Request {req.request_id} for {req.asset_name} was rejected by manager."
                ),
                priority=NotificationPriority.HIGH,
                dedup_key=f"request_manager_review:{req.request_id}:{'approved' if payload.is_approved else 'rejected'}",
                cooldown_hours=1,
                metadata={"request_id": req.request_id, "asset_name": req.asset_name, "approved": payload.is_approved},
                email_to=requester_email,
                email_subject=(
                    f"Request Approved: {req.asset_name}"
                    if payload.is_approved
                    else f"Request Rejected: {req.asset_name}"
                ),
                email_html=EmailService._wrap_email(
                    "Request Decision",
                    req.asset_name,
                    (
                        f"<p>Your request <strong>{req.request_id}</strong> has been approved.</p>"
                        if payload.is_approved
                        else f"<p>Your request <strong>{req.request_id}</strong> has been rejected.</p>"
                    ),
                    accent_color="#16a34a" if payload.is_approved else "#dc2626",
                ),
            )

        db.refresh(req)
        
        # Notify support
        support_emails = RequestService.get_emails_by_roles_in_branch(db, [EmployeeRole.SUPPORT_TEAM], req.employee.branch, user)
        EmailService.notify_manager_decision(req.employee.name, req.asset_name, payload.is_approved, support_emails)

        return RequestService._serialize_request(req)

    @staticmethod
    def update_manager_notes(db: Session, request_id: str, payload: RequestManagerNotes, user: Employee):
        with db.begin():
            req = apply_tenant_filter(db.query(Request), user, Request).filter(Request.request_id == request_id).with_for_update().first()
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")

            RequestService.validate_tenant_scope(req, user)
            RequestService.validate_branch_scope(req, user)

            old_notes = req.manager_notes
            req.manager_notes = payload.manager_notes
            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                user,
                {"manager_notes": old_notes},
                {"manager_notes": req.manager_notes},
                "MANAGER_NOTES_UPDATE",
            )

        db.refresh(req)
        return RequestService._serialize_request(req)

    @staticmethod
    def delete_request(db: Session, request_id: str, user: Employee):
        with db.begin():
            req = apply_tenant_filter(db.query(Request), user, Request).filter(Request.request_id == request_id).with_for_update().first()
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")

            if req.stage != "HR_VERIFICATION":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Requests can only be deleted before support review begins.",
                )

            if user.role == EmployeeRole.EMPLOYEE:
                if req.emp_id != user.employee_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employees can only delete their own requests.")
            else:
                RequestService.validate_tenant_scope(req, user)
                RequestService.validate_branch_scope(req, user)

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "DELETE",
                user,
                {"status": req.status, "stage": req.stage},
                None,
                "REQUEST_DELETION",
            )
            db.delete(req)

        return {"status": "deleted", "request_id": request_id}

    @staticmethod
    def review_request_by_admin(db: Session, request_id: str, payload: RequestReview, user: Employee):
        # Admin review usually means ORG_ADMIN or SUPER_ADMIN
        with db.begin():
            req = apply_tenant_filter(db.query(Request), user, Request).filter(Request.request_id == request_id).with_for_update().first()
            if not req:
                raise HTTPException(status_code=404)
            old_status = req.status
            if not payload.is_approved:
                req.status = "REJECTED"
                req.stage = "REJECTED"
            else:
                req.status = "APPROVED_FOR_SUPPORT"
                req.stage = "READY"

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                user,
                {"status": old_status},
                {"status": req.status},
                "ADMIN_OVERRIDE_REVIEW",
            )

        db.refresh(req)

        stage_recipients = RequestService._get_higher_authority_emails_for_request(db, req.employee, user)
        try:
            EmailService.notify_request_stage_update(
                employee_name=req.employee.name,
                asset_name=req.asset_name,
                branch=req.employee.branch or "-",
                stage_name=req.stage,
                recipients=stage_recipients,
            )
        except Exception as exc:
            logger.warning("Notification failure for stage update request_id=%s: %s", req.request_id, str(exc))
        return RequestService._serialize_request(req)

    @staticmethod
    def execute_asset_request(
        db: Session,
        request_id: str,
        provided_asset_id: Optional[str],
        broken_asset_id: Optional[str],
        user: Employee,
        provided_instance_id: Optional[str] = None,
        broken_instance_id: Optional[str] = None,
    ):
        decision = (provided_asset_id and ("NEW" if broken_asset_id is None else "REPLACE")) or None
        with db.begin():
            req = apply_tenant_filter(db.query(Request), user, Request).filter(Request.request_id == request_id).with_for_update().first()
            if not req:
                raise HTTPException(status_code=404)
            decision = (req.request_type or req.action_type or decision or "NEW").strip().upper()

        if decision == "NEW":
            payload = RequestAssignNew(provided_instance_id=provided_instance_id or "")
            return RequestService.assign_new_request(db, request_id, payload, user)
        if decision == "REPLACE":
            payload = RequestReplace(
                provided_instance_id=provided_instance_id or "",
                broken_instance_id=broken_instance_id,
                old_asset_disposition="DAMAGED",
            )
            return RequestService.replace_request(db, request_id, payload, user)
        if decision == "SERVICE":
            payload = RequestServiceStart(
                issue_description="Service started from legacy execute endpoint",
                service_vendor="Internal IT",
                service_cost=0.0,
                service_start_date=datetime.now(timezone.utc),
                expected_return_date=None,
                broken_instance_id=broken_instance_id,
                temporary_instance_id=provided_instance_id,
            )
            return RequestService.start_service_request(db, request_id, payload, user)

        raise HTTPException(
            status_code=400,
            detail="Request has no actionable type (NEW, REPLACE, or SERVICE). Complete help desk triage first.",
        )

    @staticmethod
    def assign_new_request(db: Session, request_id: str, payload: RequestAssignNew, user: Employee):
        try:
            req = apply_tenant_filter(db.query(Request), user, Request).filter(Request.request_id == request_id).with_for_update().first()
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")

            if req.status == RequestStatus.COMPLETED and req.instance_id == payload.provided_instance_id:
                return req

            RequestService.validate_tenant_scope(req, user)
            RequestService.validate_branch_scope(req, user)
            if (req.request_type or "").upper() != "NEW":
                raise HTTPException(status_code=400, detail="Request type is not NEW")
            if req.status not in [RequestStatus.APPROVED, "APPROVED_FOR_SUPPORT", "READY"] and req.stage != "READY":
                raise HTTPException(status_code=400, detail="Request is not ready for assignment")

            provided_instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(AssetInstance.instance_id == payload.provided_instance_id).with_for_update().first()
            if not provided_instance:
                raise HTTPException(status_code=404, detail="Provided instance not found")

            provided_asset = apply_tenant_filter(db.query(Asset), user, Asset).filter(Asset.asset_id == provided_instance.asset_id).with_for_update().first()
            if provided_asset and provided_asset.asset_usage_type == AssetUsageType.SHARED:
                raise HTTPException(status_code=400, detail="Shared assets cannot be assigned to employees")
            if provided_asset and provided_asset.asset_status == AssetStatus.IN_REPAIR:
                raise HTTPException(status_code=400, detail="Assets in IN_REPAIR cannot be assigned")

            StockService.allocate_asset(
                db,
                provided_instance.asset_id,
                req.emp_id,
                AllocationType.PERMANENT,
                user,
                f"FULFILL_REQ_{request_id}",
                instance_id=provided_instance.instance_id,
                movement_type=MovementType.ALLOCATE,
                is_temporary=False,
            )

            old_status = req.status
            req.instance_id = provided_instance.instance_id
            req.status = RequestStatus.COMPLETED
            req.stage = "COMPLETED"
            req.assigned_at = datetime.now(timezone.utc)
            req.completed_at = datetime.now(timezone.utc)

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                user,
                {"status": old_status},
                {"status": req.status, "instance_id": req.instance_id},
                "REQUEST_NEW_ASSIGNED",
            )

            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(req)
        return req

    @staticmethod
    def replace_request(db: Session, request_id: str, payload: RequestReplace, user: Employee):
        try:
            req = apply_tenant_filter(db.query(Request), user, Request).filter(Request.request_id == request_id).with_for_update().first()
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")

            if req.status == RequestStatus.COMPLETED and req.instance_id == payload.provided_instance_id:
                return req

            RequestService.validate_tenant_scope(req, user)
            RequestService.validate_branch_scope(req, user)
            if (req.request_type or "").upper() != "REPLACE":
                raise HTTPException(status_code=400, detail="Request type is not REPLACE")
            if req.status not in [RequestStatus.APPROVED, "APPROVED_FOR_SUPPORT", "READY"] and req.stage != "READY":
                raise HTTPException(status_code=400, detail="Request is not ready for replacement")

            new_instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(AssetInstance.instance_id == payload.provided_instance_id).with_for_update().first()
            if not new_instance:
                raise HTTPException(status_code=404, detail="Replacement instance not found")
            if new_instance.status != AssetStatus.AVAILABLE:
                raise HTTPException(status_code=400, detail="Replacement asset must be AVAILABLE")

            old_instance_id = payload.broken_instance_id or req.instance_id
            if not old_instance_id:
                raise HTTPException(status_code=400, detail="Broken instance is required for replacement")
            old_instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(AssetInstance.instance_id == old_instance_id).with_for_update().first()
            if not old_instance:
                raise HTTPException(status_code=404, detail="Broken instance not found")

            new_asset = apply_tenant_filter(db.query(Asset), user, Asset).filter(Asset.asset_id == new_instance.asset_id).first()
            old_asset = apply_tenant_filter(db.query(Asset), user, Asset).filter(Asset.asset_id == old_instance.asset_id).first()
            if (new_asset and new_asset.asset_usage_type == AssetUsageType.SHARED) or (old_asset and old_asset.asset_usage_type == AssetUsageType.SHARED):
                raise HTTPException(status_code=400, detail="Shared assets cannot be used in replacement assignment")
            if (new_asset and new_asset.asset_status == AssetStatus.IN_REPAIR) or (old_asset and old_asset.asset_status == AssetStatus.IN_REPAIR):
                raise HTTPException(status_code=400, detail="Assets in IN_REPAIR cannot be replaced")
            if new_asset and old_asset and new_asset.category_id != old_asset.category_id:
                raise HTTPException(status_code=400, detail="Replacement asset must be from the same category")

            StockService.allocate_asset(
                db,
                new_instance.asset_id,
                req.emp_id,
                AllocationType.PERMANENT,
                user,
                f"REPLACE_REQ_{request_id}",
                instance_id=new_instance.instance_id,
                movement_type=MovementType.REPLACE,
                is_temporary=False,
            )

            if payload.old_asset_disposition == "RETIRED":
                StockService.retire_instance(db, old_instance.instance_id, user, reason=f"REPLACED_REQ_{request_id}")
            else:
                StockService.mark_damaged(db, old_instance.instance_id, user, reason=f"REPLACED_REQ_{request_id}")

            from app.server.services.lifecycle_service import LifecycleService

            LifecycleService.log_event(
                db,
                instance_id=new_instance.instance_id,
                asset_id=new_instance.asset_id,
                event_type=LifecycleEvent.REPLACED,
                performed_by=user,
                old_status=AssetStatus.AVAILABLE.value,
                new_status=AssetStatus.ASSIGNED.value,
                notes=f"Replaced instance {old_instance.instance_id}",
                organization_id=req.organization_id,
                metadata={"request_id": req.request_id, "replaced_instance_id": old_instance.instance_id},
            )

            old_status = req.status
            req.serviced_instance_id = old_instance.instance_id
            req.instance_id = new_instance.instance_id
            req.status = RequestStatus.COMPLETED
            req.stage = "COMPLETED"
            req.assigned_at = datetime.now(timezone.utc)
            req.completed_at = datetime.now(timezone.utc)

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                user,
                {"status": old_status},
                {
                    "status": req.status,
                    "instance_id": req.instance_id,
                    "serviced_instance_id": req.serviced_instance_id,
                    "old_asset_disposition": payload.old_asset_disposition,
                },
                "REQUEST_REPLACED",
            )

            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(req)
        return req

    @staticmethod
    def start_service_request(db: Session, request_id: str, payload: RequestServiceStart, user: Employee):
        try:
            req = apply_tenant_filter(db.query(Request), user, Request).filter(Request.request_id == request_id).with_for_update().first()
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")
            RequestService.validate_tenant_scope(req, user)
            RequestService.validate_branch_scope(req, user)
            if (req.request_type or "").upper() != "SERVICE":
                raise HTTPException(status_code=400, detail="Request type is not SERVICE")
            if req.status not in [RequestStatus.APPROVED, "APPROVED_FOR_SUPPORT", "READY", RequestStatus.ASSIGNED] and req.stage not in {"READY", "WIP_SERVICE", "IN_REPAIR"}:
                raise HTTPException(status_code=400, detail="Request is not ready for service")
            if payload.service_cost is None:
                raise HTTPException(status_code=400, detail="Service must log cost")
            if not payload.broken_instance_id and not req.instance_id:
                raise HTTPException(status_code=400, detail="broken_instance_id is required for service start")

            broken_instance_id = payload.broken_instance_id or req.instance_id
            if not broken_instance_id:
                raise HTTPException(status_code=400, detail="Broken instance is required for service")

            if req.status == RequestStatus.IN_REPAIR and req.instance_id == broken_instance_id:
                return req

            broken_instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(AssetInstance.instance_id == broken_instance_id).with_for_update().first()
            if not broken_instance:
                raise HTTPException(status_code=404, detail="Broken instance not found")

            broken_asset = apply_tenant_filter(db.query(Asset), user, Asset).filter(Asset.asset_id == broken_instance.asset_id).with_for_update().first()
            if broken_asset and broken_asset.asset_usage_type == AssetUsageType.SHARED:
                raise HTTPException(status_code=400, detail="Shared assets cannot be employee-service assigned")

            StockService.mark_in_repair(
                db,
                broken_instance.instance_id,
                user,
                reason=f"SERVICE_START_{request_id}",
                repair_cost=0.0,
            )

            repair_tracking = Tracking(
                asset_id=broken_instance.asset_id,
                instance_id=broken_instance.instance_id,
                emp_id=req.emp_id,
                organization_id=req.organization_id,
                branch_id=req.branch_id,
                movement_type=MovementType.REPAIR,
                allocation_type=AllocationType.PERMANENT,
                movement_reason=f"SERVICE_START_{request_id}",
            )
            db.add(repair_tracking)

            if payload.temporary_instance_id:
                temp_instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(AssetInstance.instance_id == payload.temporary_instance_id).with_for_update().first()
                if not temp_instance:
                    raise HTTPException(status_code=404, detail="Temporary asset instance not found")
                if temp_instance.status != AssetStatus.AVAILABLE:
                    raise HTTPException(status_code=400, detail="Temporary asset cannot be already assigned")

                temp_asset = apply_tenant_filter(db.query(Asset), user, Asset).filter(Asset.asset_id == temp_instance.asset_id).first()
                if temp_asset and temp_asset.asset_usage_type == AssetUsageType.SHARED:
                    raise HTTPException(status_code=400, detail="Shared assets cannot be assigned to employee")
                if broken_asset and temp_asset and broken_asset.category_id != temp_asset.category_id:
                    raise HTTPException(status_code=400, detail="Temporary asset must match category of serviced asset")

                temp_tracking = StockService.allocate_asset(
                    db,
                    temp_instance.asset_id,
                    req.emp_id,
                    AllocationType.TEMPORARY,
                    user,
                    reason=f"TEMP_ASSIGNED_REQ_{request_id}",
                    instance_id=temp_instance.instance_id,
                    movement_type=MovementType.TEMP_ASSIGNED,
                    is_temporary=True,
                )

                db.flush()
                temp_instance.status = AssetStatus.ASSIGNED

                from app.server.services.lifecycle_service import LifecycleService

                LifecycleService.log_event(
                    db,
                    instance_id=temp_instance.instance_id,
                    asset_id=temp_instance.asset_id,
                    event_type=LifecycleEvent.TEMP_ASSIGNED,
                    performed_by=user,
                    old_status=AssetStatus.AVAILABLE.value,
                    new_status=AssetStatus.ASSIGNED.value,
                    notes=f"Temporary assignment for request {request_id}",
                    tracking_id=temp_tracking.tracking_id,
                    organization_id=req.organization_id,
                    metadata={"request_id": request_id, "is_temporary": True},
                )
                req.temporary_instance_id = temp_instance.instance_id
                req.temporary_tracking_id = temp_tracking.tracking_id

            old_status = req.status
            req.instance_id = broken_instance.instance_id
            req.serviced_asset_id = broken_instance.asset_id
            req.service_issue_description = payload.issue_description
            req.service_vendor = payload.service_vendor
            req.service_cost = float(payload.service_cost)
            req.service_start_date = payload.service_start_date
            req.expected_return_date = payload.expected_return_date
            req.status = RequestStatus.IN_REPAIR
            req.stage = "IN_REPAIR"

            # SLA tracking starts with service start.
            req.sla_due = payload.expected_return_date or (payload.service_start_date + timedelta(hours=RequestService._urgency_sla_hours(req.urgency)))
            now_utc = datetime.now(timezone.utc)
            req.sla_breached = bool(req.sla_due and now_utc > req.sla_due)

            if req.sla_breached:
                try:
                    NotificationService.emit(
                        db,
                        actor=user,
                        recipient_scope=f"BRANCH:{req.branch_id or '-'}",
                        event_type="SERVICE_SLA_BREACHED",
                        title="Service SLA delayed",
                        message=f"Service request {req.request_id} breached SLA at start.",
                        priority=NotificationPriority.HIGH,
                        dedup_key=f"service_sla_breached_start:{req.request_id}",
                        cooldown_hours=24,
                        metadata={"request_id": req.request_id, "sla_due": req.sla_due.isoformat() if req.sla_due else None},
                    )
                except Exception as exc:
                    logger.warning("Notification failure for service SLA request_id=%s: %s", req.request_id, str(exc))

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                user,
                {"status": old_status},
                {
                    "status": req.status,
                    "service_vendor": req.service_vendor,
                    "service_cost": req.service_cost,
                    "temporary_instance_id": req.temporary_instance_id,
                    "sla_due": req.sla_due.isoformat() if req.sla_due else None,
                    "sla_breached": req.sla_breached,
                },
                "SERVICE_STARTED",
            )

            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(req)
        return req

    @staticmethod
    def cancel_asset_request(db: Session, request_id: str, current_user: Employee):
        """Cancel request. SUBMITTED or HR_VALIDATED -> CANCELLED. Rollback reserved instances."""
        with db.begin():
            req = apply_tenant_filter(db.query(Request), current_user, Request).filter(
                Request.request_id == request_id
            ).with_for_update().first()

            if not req:
                raise HTTPException(status_code=404, detail="Request not found")

            RequestService.validate_tenant_scope(req, current_user)
            RequestService.validate_branch_scope(req, current_user)

            # Only allow cancellation from SUBMITTED, HR_VALIDATED, or TRIAGED
            if req.status not in [RequestStatus.SUBMITTED, RequestStatus.HR_VALIDATED, RequestStatus.TRIAGED]:
                raise HTTPException(status_code=400, detail=f"Cannot cancel request in {req.status} state")

            # Employee can only cancel their own request
            if current_user.role == EmployeeRole.EMPLOYEE and req.emp_id != current_user.employee_id:
                raise HTTPException(status_code=403, detail="You can only cancel your own requests")

            # If TRIAGED, rollback reserved instance
            if req.status == RequestStatus.TRIAGED and req.instance_id:
                instance = apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance).filter(
                    AssetInstance.instance_id == req.instance_id
                ).with_for_update().first()

                if instance and instance.status == "RESERVED":
                    instance.status = "AVAILABLE"  # Rollback

            old_status = req.status
            req.status = RequestStatus.CANCELLED
            req.cancelled_at = datetime.now(timezone.utc)
            req.request_locked = False

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                current_user,
                {"status": old_status},
                {"status": req.status},
                "REQUEST_CANCELLED",
            )

        db.refresh(req)
        
        return RequestService._serialize_request(req)

    @staticmethod
    def resolve_service_request(db: Session, request_id: str, payload: RequestResolve, user: Employee):
        complete_payload = RequestServiceComplete(
            resolution_notes=payload.resolution_notes,
            repair_cost=float(payload.repair_cost or 0.0),
            repaired_instance_id=None,
        )
        return RequestService.complete_service_request(db, request_id, complete_payload, user)

    @staticmethod
    def complete_service_request(db: Session, request_id: str, payload: RequestServiceComplete, user: Employee):
        try:
            req = apply_tenant_filter(db.query(Request), user, Request).filter(Request.request_id == request_id).with_for_update().first()
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")

            if req.status == RequestStatus.COMPLETED:
                return req

            RequestService.validate_tenant_scope(req, user)
            RequestService.validate_branch_scope(req, user)
            if (req.request_type or "").upper() != "SERVICE":
                raise HTTPException(status_code=400, detail="Request type is not SERVICE")
            if req.status not in [RequestStatus.IN_REPAIR, RequestStatus.WIP_SERVICE, RequestStatus.ASSIGNED] and req.stage not in {"IN_REPAIR", "WIP_SERVICE"}:
                raise HTTPException(status_code=400, detail="No active service request found")
            if not (payload.resolution_notes or "").strip():
                raise HTTPException(status_code=400, detail="resolution_notes is required for service completion")

            repaired_instance_id = payload.repaired_instance_id or req.instance_id
            if not repaired_instance_id:
                raise HTTPException(status_code=400, detail="Repaired instance is required")

            repaired_instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(AssetInstance.instance_id == repaired_instance_id).with_for_update().first()
            if not repaired_instance:
                raise HTTPException(status_code=404, detail="Repaired instance not found")

            repaired_asset = apply_tenant_filter(db.query(Asset), user, Asset).filter(Asset.asset_id == repaired_instance.asset_id).with_for_update().first()
            if repaired_asset and repaired_asset.asset_usage_type == AssetUsageType.SHARED:
                raise HTTPException(status_code=400, detail="Shared assets cannot be completed through employee service workflow")

            StockService.mark_repaired(db, repaired_instance.instance_id, user, reason=f"SERVICE_COMPLETE_{request_id}")

            # Enforce status transition after service completion.
            repaired_instance.status = AssetStatus.AVAILABLE

            repaired_tracking = Tracking(
                asset_id=repaired_instance.asset_id,
                instance_id=repaired_instance.instance_id,
                emp_id=req.emp_id,
                organization_id=req.organization_id,
                branch_id=req.branch_id,
                movement_type=MovementType.REPAIRED,
                allocation_type=AllocationType.PERMANENT,
                movement_reason=f"SERVICE_COMPLETE_{request_id}",
            )
            db.add(repaired_tracking)

            service_cost = float(req.service_cost if req.service_cost is not None else payload.repair_cost)
            if service_cost < 0:
                raise HTTPException(status_code=400, detail="service_cost cannot be negative")

            old_instance_cost = float(repaired_instance.repair_cost_total or 0.0)
            repaired_instance.repair_cost_total = old_instance_cost + service_cost

            old_asset_cost = float(repaired_asset.repair_total_cost or 0.0) if repaired_asset else 0.0
            if repaired_asset:
                repaired_asset.repair_total_cost = old_asset_cost + service_cost
                if service_cost > 0:
                    repaired_asset.repair_count = int(repaired_asset.repair_count or 0) + 1

            AuditService.log_change(
                db,
                "asset_instances",
                repaired_instance.instance_id,
                "UPDATE",
                user,
                {"repair_cost_total": old_instance_cost},
                {"repair_cost_total": float(repaired_instance.repair_cost_total or 0.0)},
                "SERVICE_COST_AGGREGATED",
            )

            if repaired_asset:
                AuditService.log_change(
                    db,
                    "assets",
                    repaired_asset.asset_id,
                    "UPDATE",
                    user,
                    {"repair_total_cost": old_asset_cost},
                    {"repair_total_cost": float(repaired_asset.repair_total_cost or 0.0)},
                    "SERVICE_COST_AGGREGATED",
                )

            if req.temporary_tracking_id:
                temp_tracking = apply_tenant_filter(db.query(Tracking), user, Tracking).filter(
                    Tracking.tracking_id == req.temporary_tracking_id,
                    Tracking.returned_at == None,
                ).with_for_update().first()
                if temp_tracking:
                    StockService.return_asset(db, temp_tracking.tracking_id, user, reason=f"TEMP_RETURN_REQ_{request_id}", status_override=AssetStatus.AVAILABLE)

                    if temp_tracking.instance_id:
                        temp_instance = apply_tenant_filter(db.query(AssetInstance), user, AssetInstance).filter(AssetInstance.instance_id == temp_tracking.instance_id).with_for_update().first()
                        if temp_instance:
                            temp_instance.status = AssetStatus.AVAILABLE

                    temp_return_tracking = Tracking(
                        asset_id=temp_tracking.asset_id,
                        instance_id=temp_tracking.instance_id,
                        emp_id=req.emp_id,
                        organization_id=req.organization_id,
                        branch_id=req.branch_id,
                        movement_type=MovementType.TEMP_RETURNED,
                        allocation_type=AllocationType.TEMPORARY,
                        movement_reason=f"TEMP_RETURN_REQ_{request_id}",
                        is_temporary=True,
                    )
                    db.add(temp_return_tracking)

                    from app.server.services.lifecycle_service import LifecycleService

                    if temp_tracking.instance_id:
                        LifecycleService.log_event(
                            db,
                            instance_id=temp_tracking.instance_id,
                            asset_id=temp_tracking.asset_id,
                            event_type=LifecycleEvent.TEMP_RETURNED,
                            performed_by=user,
                            old_status=AssetStatus.ASSIGNED.value,
                            new_status=AssetStatus.AVAILABLE.value,
                            notes=f"Temporary asset returned for request {request_id}",
                            tracking_id=temp_return_tracking.tracking_id,
                            organization_id=req.organization_id,
                            metadata={"request_id": request_id, "is_temporary": True},
                        )

            old_status = req.status
            req.status = RequestStatus.COMPLETED
            req.stage = "COMPLETED"
            req.completed_at = datetime.now(timezone.utc)

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                user,
                {"status": old_status},
                {
                    "status": req.status,
                    "completed_at": req.completed_at.isoformat() if req.completed_at else None,
                    "resolution_notes": payload.resolution_notes,
                    "repair_cost": float(payload.repair_cost),
                    "service_cost_aggregated": service_cost,
                },
                "SERVICE_COMPLETED",
            )

            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(req)
        return req

    @staticmethod
    def try_auto_allocate_for_asset(db: Session, asset_id: str, user: Employee, trigger_reason: str = "AUTO_REALLOCATION"):
        asset = (
            apply_tenant_filter(db.query(Asset), user, Asset)
            .options(joinedload(Asset.category))
            .filter(Asset.asset_id == asset_id)
            .first()
        )
        if not asset or asset.unused <= 0 or not asset.category:
            return None

        req = (
            apply_tenant_filter(db.query(Request), user, Request)
            .join(Request.employee)
            .filter(
                Request.stage == "READY",
                Request.status == "APPROVED_FOR_SUPPORT",
                Request.action_type.in_(["NEW", "REPLACE"]),
                Request.asset_category == asset.category.category_name,
                Employee.branch_id == asset.branch_id,
                Employee.is_active == True,
            )
            .order_by(Request.req_date.asc())
            .with_for_update()
            .first()
        )
        if not req:
            return None

        candidate_assets = (
            db.query(Asset)
            .options(joinedload(Asset.category))
            .filter(
                Asset.branch_id == asset.branch_id,
                Asset.unused > 0,
            )
            .all()
        )
        candidate_assets = [
            candidate
            for candidate in candidate_assets
            if candidate.category and asset.category and candidate.category.category_name == asset.category.category_name
        ]
        if not candidate_assets:
            return None

        from app.server.services.asset_insights_service import AssetInsightsService

        best_asset = max(
            candidate_assets,
            key=lambda candidate: (
                AssetInsightsService.get_asset_health(db, candidate.asset_id).health_score,
                -(candidate.repair_count or 0),
                candidate.purchased_date or date.min,
            ),
        )

        StockService.allocate_asset(
            db,
            best_asset.asset_id,
            req.emp_id,
            AllocationType.PERMANENT,
            user,
            f"{trigger_reason}_{req.request_id}",
        )
        req.status = "COMPLETED"
        req.stage = "COMPLETED"
        AuditService.log_change(
            db,
            "requests",
            req.request_id,
            "UPDATE",
            user,
            {"status": "APPROVED_FOR_SUPPORT", "stage": "READY"},
            {"status": req.status, "stage": req.stage, "asset_id": best_asset.asset_id},
            trigger_reason,
        )
        return req

    @staticmethod
    def request_cross_branch_transfer(db: Session, request_id: str, payload: "RequestCrossBranchTransfer", user: Employee):
        with db.begin():
            req = apply_tenant_filter(db.query(Request), user, Request).filter(Request.request_id == request_id).with_for_update().first()
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")

            if user.role != EmployeeRole.MANAGER:
                raise HTTPException(status_code=403, detail="Only Managers can initiate a cross-branch transfer")
            RequestService.validate_tenant_scope(req, user)
            RequestService.validate_branch_scope(req, user)

            target_branch = RequestService._resolve_active_branch(db, payload.target_branch, user)
            if not target_branch:
                raise HTTPException(status_code=400, detail=f"Target branch '{payload.target_branch}' is not a valid active branch.")

            target_branch_name = target_branch.branch_name

            if (req.employee.branch_id and req.employee.branch_id == target_branch.branch_id) or (
                (req.employee.branch or "").strip().lower() == target_branch_name.strip().lower()
            ):
                raise HTTPException(status_code=400, detail="Cannot request transfer from your own branch")

            # Find target branch stakeholders
            target_manager_email = RequestService.get_manager_email_for_branch(db, target_branch_name, user)
            if not target_manager_email:
                raise HTTPException(status_code=400, detail=f"Target branch '{target_branch_name}' has no active Manager to receive this request.")

            target_support_emails = RequestService.get_emails_by_roles_in_branch(
                db,
                [EmployeeRole.SUPPORT_TEAM],
                target_branch_name,
                user,
            )

            # Update Request Status
            old_status = req.status
            req.status = "AWAITING_TRANSFER"
            req.action_type = f"TRANSFER:{target_branch_name}"
            transfer_tracking = None
            if req.serviced_asset_id:
                service_asset = apply_tenant_filter(db.query(Asset), user, Asset).filter(Asset.asset_id == req.serviced_asset_id).with_for_update().first()
                if service_asset and service_asset.asset_status == AssetStatus.IN_REPAIR:
                    raise HTTPException(status_code=400, detail="Assets in IN_REPAIR cannot be transferred")

                transfer_tracking = Tracking(
                    asset_id=req.serviced_asset_id,
                    asset_name=req.asset_name,
                    emp_id=req.emp_id,
                    organization_id=user.organization_id,
                    branch_id=user.branch_id,
                    category=req.asset_category,
                    branch=req.employee.branch,
                    from_branch=req.employee.branch,
                    to_branch=target_branch_name,
                    movement_type=MovementType.TRANSFER,
                    movement_reason=f"CROSS_BRANCH_REQUEST_{request_id}",
                    allocation_type=AllocationType.TEMPORARY,
                    transfer_status="PENDING",
                )
                db.add(transfer_tracking)
                db.flush()

            AuditService.log_change(
                db,
                "requests",
                request_id,
                "UPDATE",
                user,
                {"status": old_status},
                {"status": req.status, "action": req.action_type},
                "CROSS_BRANCH_REQUEST",
            )
            if transfer_tracking:
                AuditService.log_change(
                    db,
                    "tracking",
                    transfer_tracking.tracking_id,
                    "CREATE",
                    user,
                    None,
                    {
                        "asset_name": transfer_tracking.asset_name,
                        "emp_id": transfer_tracking.emp_id,
                        "from_branch": transfer_tracking.from_branch,
                        "to_branch": transfer_tracking.to_branch,
                        "movement_type": transfer_tracking.movement_type.value,
                        "transfer_status": transfer_tracking.transfer_status,
                    },
                    "CROSS_BRANCH_REQUEST",
                )

        db.refresh(req)

        # Send Email
        recipients = [target_manager_email] + target_support_emails
        try:
            EmailService.notify_cross_branch_transfer_request(
                requester_branch=req.employee.branch,
                target_branch=target_branch_name,
                asset_name=req.asset_name,
                recipients=recipients,
                reply_to_email=user.email
            )
        except Exception as exc:
            logger.warning("Notification failure for cross-branch transfer request_id=%s: %s", req.request_id, str(exc))
        return req

    @staticmethod
    def get_emails_by_roles_in_branch(db: Session, roles: List[EmployeeRole], branch: str, current_user: Employee) -> List[str]:
        resolved_branch = RequestService._resolve_active_branch(db, branch, current_user)
        normalized = (branch or "").strip().lower()

        stakeholders_query = apply_tenant_filter(db.query(Employee), current_user, Employee).join(
            Branch,
            Employee.branch_id == Branch.branch_id,
            isouter=True,
        ).filter(
            Employee.role.in_(roles),
            Employee.is_active == True,  # noqa: E712
        )

        if resolved_branch:
            stakeholders_query = stakeholders_query.filter(
                or_(
                    Employee.branch_id == resolved_branch.branch_id,
                    func.lower(Branch.branch_name) == resolved_branch.branch_name.strip().lower(),
                )
            )
        else:
            stakeholders_query = stakeholders_query.filter(func.lower(Branch.branch_name) == normalized)

        stakeholders = stakeholders_query.all()
        return [EmailService.delivery_email(s) for s in stakeholders if EmailService.delivery_email(s)]

    @staticmethod
    def get_admin_emails(db: Session, current_user: Employee) -> List[str]:
        from sqlalchemy import or_, and_
        # Notify global SUPER_ADMINs and the organization's ORG_ADMINs
        admins = db.query(Employee).filter(
            Employee.is_active == True,
            or_(
                Employee.role == EmployeeRole.SUPER_ADMIN,
                and_(
                    Employee.role == EmployeeRole.ORG_ADMIN,
                    Employee.organization_id == (current_user.organization_id if current_user else None)
                )
            )
        ).all()
        return [EmailService.delivery_email(a) for a in admins if EmailService.delivery_email(a)]
