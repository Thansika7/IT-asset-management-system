from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func as sql_func
from fastapi import HTTPException, status
from typing import List, Optional

from app.server.models.request import (
    RequestCreate,
    RequestFormAssetOption,
    RequestFormOptions,
    RequestHRVerify,
    RequestResolve,
    RequestReview,
    RequestTriage,
)
from app.server.schema.request import Request
from app.server.schema.asset import Asset, AssetStatus
from app.server.schema.tracking import Tracking, MovementType, AllocationType
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.category import Category
from app.server.services.email_service import EmailService
from app.server.services.stock_service import StockService
from app.server.services.account_service import AccountService
from app.server.services.audit_service import AuditService


class RequestService:
    FORM_CATEGORIES = ["Laptop", "Monitor", "Keyboard", "Mouse", "Printer", "Phone", "Accessory", "Software", "Other"]
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
        priority = (req.priority or "P3").upper()
        req_date = req.req_date
        if req_date:
            sla_target = req_date + timedelta(hours=RequestService.SLA_HOURS.get(priority, 24))
            data.sla_target_at = sla_target
            now = datetime.now(req_date.tzinfo) if req_date.tzinfo else datetime.now(timezone.utc).replace(tzinfo=None)
            data.sla_breached = req.stage not in {"COMPLETED", "REJECTED"} and sla_target < now
        severity = (req.severity or "MEDIUM").upper()
        data.severity_description = RequestService.SEVERITY_DESCRIPTIONS.get(severity)
        data.priority_description = RequestService.PRIORITY_DESCRIPTIONS.get(priority)
        data.priority_response_time = RequestService.PRIORITY_RESPONSE_TIME.get(priority)
        urgency = (req.urgency or "MEDIUM").upper()
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
    def get_request_form_options(db: Session, current_user: Employee) -> RequestFormOptions:
        categories = sorted(set(RequestService.FORM_CATEGORIES + [row[0] for row in db.query(Category.category_name).all() if row[0]]))

        known_assets: list[RequestFormAssetOption] = []
        if current_user.role == EmployeeRole.EMPLOYEE:
            rows = (
                db.query(Tracking, Asset, Category)
                .join(Asset, Tracking.asset_id == Asset.asset_id)
                .outerjoin(Category, Asset.category_id == Category.category_id)
                .filter(
                    Tracking.emp_id == current_user.employee_id,
                    Tracking.returned_at == None,
                )
                .all()
            )
            known_assets = [
                RequestFormAssetOption(
                    asset_id=asset.asset_id,
                    asset_name=asset.name,
                    category=category.category_name if category else None,
                    sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
                    branch=asset.branch,
                    owned_by_requester=True,
                )
                for _, asset, category in rows
            ]
        else:
            query = db.query(Asset).options(joinedload(Asset.category), joinedload(Asset.sub_category))
            if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM]:
                query = query.filter(Asset.branch == current_user.branch)
            known_assets = [
                RequestFormAssetOption(
                    asset_id=asset.asset_id,
                    asset_name=asset.name,
                    category=asset.category.category_name if asset.category else None,
                    sub_category=asset.sub_category.sub_category_name if asset.sub_category else None,
                    branch=asset.branch,
                    owned_by_requester=False,
                )
                for asset in query.order_by(Asset.name.asc()).limit(50).all()
            ]

        return RequestFormOptions(
            categories=categories,
            reasons_by_category=RequestService.REASON_TEMPLATES,
            known_assets=known_assets,
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
    ):
        query = db.query(Request).options(joinedload(Request.employee))

        if current_user.role == EmployeeRole.ADMIN:
            pass
        elif current_user.role in [EmployeeRole.SUPPORT_TEAM, EmployeeRole.HR, EmployeeRole.MANAGER]:
            effective_branch = current_user.branch
            query = query.join(Request.employee).filter(Employee.branch == effective_branch)
        else:
            query = query.filter(Request.emp_id == current_user.employee_id)

        if status:
            query = query.filter(Request.status == status.strip())
        if priority:
            query = query.filter(Request.priority == priority.strip().upper())
        if severity:
            query = query.filter(Request.severity == severity.strip().upper())
        if urgency:
            query = query.filter(Request.urgency == urgency.strip().upper())

        rows = query.all()
        if sort_by_priority:
            rows = sorted(
                rows,
                key=lambda req: (
                    RequestService._compute_escalation_state(req)[0],
                    RequestService.PRIORITY_ORDER.get((req.priority or "P3").upper(), 0),
                    req.req_date,
                ),
                reverse=True,
            )
        else:
            rows = sorted(rows, key=lambda req: req.req_date, reverse=True)
        return [RequestService._serialize_request(req) for req in rows]

    @staticmethod
    def get_inventory_across_branches(db: Session, category_name: str):
        from app.server.schema.category import Category

        query = db.query(
            Asset.branch,
            Asset.brand,
            Asset.name,
            func.sum(Asset.unused).label("available_quantity")
        ).join(Category).filter(
            Category.category_name == category_name,
            Asset.unused > 0
        )
        return query.group_by(Asset.branch, Asset.brand, Asset.name).all()

    @staticmethod
    def get_manager_email_for_branch(db: Session, branch: str) -> str | None:
        manager = db.query(Employee).filter(
            Employee.branch == branch,
            Employee.role == EmployeeRole.MANAGER,
            Employee.is_active == True,
        ).first()
        return manager.email if manager else None

    @staticmethod
    def create_asset_request(db: Session, payload: RequestCreate, current_user: Employee):
        allowed_roles = [
            EmployeeRole.EMPLOYEE,
            EmployeeRole.MANAGER,
            EmployeeRole.HR,
            EmployeeRole.ADMIN,
            EmployeeRole.SUPPORT_TEAM,
        ]
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {current_user.role} is not authorized to create requests.",
            )

        if current_user.role == EmployeeRole.EMPLOYEE:
            if payload.action_type is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Employees cannot categorize requests. Support must set NEW, SERVICE, or REPLACE during triage.",
                )
            if payload.priority is not None or payload.severity is not None or payload.urgency is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Employees cannot set severity, urgency, or priority. Support assigns those during triage.",
                )
        if payload.priority is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Priority is system-derived from severity, urgency, and asset impact rules.",
            )

        # 2. Initialize Request: Start at HR Verification as planned
        req = Request(
            emp_id=current_user.employee_id,
            asset_name=payload.asset_name,
            asset_category=payload.asset_category,
            reason=payload.reason,
            action_type=None,
            priority="P3",
            severity="MEDIUM",
            urgency="MEDIUM",
            status="PENDING_SUPPORT",
            stage="HR_VERIFICATION",
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        
        AuditService.log_change(db, "requests", req.request_id, "CREATE", current_user, None, {
            "status": req.status,
            "asset_name": req.asset_name,
            "role": current_user.role
        }, "USER_SUBMISSION")

        # 3. Branch-Specific Notification Logic
        # We find stakeholders in the SAME branch, AND all Global Admins
        recipients = []
        admin_emails = RequestService.get_admin_emails(db)
        
        if current_user.role == EmployeeRole.EMPLOYEE:
            recipients = RequestService.get_emails_by_roles_in_branch(
                db, [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM], current_user.branch
            )
        elif current_user.role == EmployeeRole.HR:
            recipients = RequestService.get_emails_by_roles_in_branch(
                db, [EmployeeRole.MANAGER, EmployeeRole.SUPPORT_TEAM], current_user.branch
            )
        elif current_user.role == EmployeeRole.MANAGER:
            recipients = RequestService.get_emails_by_roles_in_branch(
                db, [EmployeeRole.SUPPORT_TEAM], current_user.branch
            )
            EmailService.notify_admin_of_manager_request(current_user.name, payload.asset_name, admin_emails)
        elif current_user.role == EmployeeRole.ADMIN:
            recipients = RequestService.get_emails_by_roles_in_branch(
                db,
                [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM],
                current_user.branch or "",
            )
        elif current_user.role == EmployeeRole.SUPPORT_TEAM:
            recipients = RequestService.get_emails_by_roles_in_branch(
                db, [EmployeeRole.MANAGER, EmployeeRole.HR], current_user.branch
            )

        recipients.extend(admin_emails)

        # 4. Immediate Automated Notifications
        EmailService.notify_branch_stakeholders(
            current_user.name, payload.asset_name, recipients, current_user.role, current_user.branch
        )
        
        # B. Notify Requester (Confirmation)
        EmailService.notify_requester_confirmation(
            current_user.email, current_user.name, payload.asset_name, current_user.branch
        )

        db.refresh(req)
        return RequestService._serialize_request(req)

    @staticmethod
    def review_request_by_hr(db: Session, request_id: str, payload: RequestHRVerify, user: Employee):
        req = db.query(Request).filter(
            Request.request_id == request_id,
            Request.stage == "HR_VERIFICATION",
        ).with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found or not in HR stage")
        if user.role != EmployeeRole.ADMIN and req.employee.branch != user.branch:
            raise HTTPException(status_code=403, detail="HR can review only requests from their own branch.")

        old_status = req.status
        req.hr_verified = payload.is_needed
        if payload.is_needed:
            req.stage = "HELPDESK_TRIAGE"
            req.status = "PENDING_SUPPORT_TRIAGE"
        else:
            req.stage = "REJECTED"
            req.status = "REJECTED"
            req.action_type = None
            req.priority = "P3"
            req.severity = "MEDIUM"
            req.urgency = "MEDIUM"
        
        db.commit()
        db.refresh(req)

        AuditService.log_change(
            db,
            "requests",
            request_id,
            "UPDATE",
            user,
            {"status": old_status},
            {"status": req.status, "hr_verified": req.hr_verified, "stage": req.stage},
            "HR_VERIFICATION",
        )

        if payload.is_needed:
            support_emails = RequestService.get_emails_by_roles_in_branch(db, [EmployeeRole.SUPPORT_TEAM], req.employee.branch)
            EmailService.notify_hr_verified(req.employee.name, req.asset_name, payload.is_needed, support_emails)
        return RequestService._serialize_request(req)

    @staticmethod
    def triage_asset_request(db: Session, request_id: str, payload: RequestTriage, user: Employee):
        req = db.query(Request).filter(
            Request.request_id == request_id,
            Request.stage == "HELPDESK_TRIAGE",
        ).with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found or not in Help Desk triage stage")
        if user.role != EmployeeRole.ADMIN and req.employee.branch != user.branch:
            raise HTTPException(status_code=403, detail="Support can triage only requests from their own branch.")
        
        requested_action = (payload.action_type or "").strip()
        selected_target = None
        if ":" in requested_action:
            requested_action, selected_target = requested_action.split(":", 1)
            requested_action = requested_action.strip()
            selected_target = selected_target.strip()
        if not requested_action:
            raise HTTPException(status_code=400, detail="Support must categorize the request before triage.")

        local_stock = db.query(sql_func.sum(Asset.unused)).join(Category).filter(
            Asset.branch == req.employee.branch,
            Category.category_name == req.asset_category,
        ).scalar() or 0

        stock_msg = ""
        if local_stock > 0:
            req.status = f"Available in local branch: {req.employee.branch}"
            stock_msg = req.status
        else:
            other_stocks = RequestService.get_inventory_across_branches(db, req.asset_category)
            if not other_stocks:
                req.status = "Unavailable in all branches"
                stock_msg = req.status
            else:
                # Group presentation by branch for readability
                # Result rows have: branch, brand, name, available_quantity
                branch_details = {}
                for s in other_stocks:
                    brand_name = s.brand or 'Unknown Brand'
                    detail = f"{s.available_quantity}x {brand_name} ({s.name})"
                    if s.branch not in branch_details:
                        branch_details[s.branch] = []
                    branch_details[s.branch].append(detail)
                
                branches_info = ", ".join([f"{b} [{', '.join(details)}]" for b, details in branch_details.items()])
                req.status = f"Unavailable locally. Available in: {branches_info}"
                stock_msg = req.status
                if selected_target:
                    req.status += f" (Selected: {selected_target})"

        req.action_type = requested_action
        req.severity = payload.severity.value
        req.urgency = RequestService._derive_urgency(req, req.severity, payload.affected_users, requested_action)
        req.priority = RequestService._derive_priority(req, req.severity, req.urgency, payload.affected_users)

        requester = req.employee
        if requester.role == EmployeeRole.MANAGER:
            req.status = "PENDING_ADMIN"
            req.stage = "ADMIN_APPROVAL"
            admin_emails = RequestService.get_admin_emails(db)
            EmailService.notify_admin_of_manager_request(requester.name, req.asset_name, admin_emails)
        elif user.role == EmployeeRole.ADMIN:
            req.status = "APPROVED_FOR_SUPPORT"
            req.stage = "READY"
        else:
            req.status = "PENDING_MANAGER"
            req.stage = "MANAGER_APPROVAL"

        db.commit()
        db.refresh(req)
        
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, 
                                {"status": "PENDING_SUPPORT"}, {"status": req.status, "action": req.action_type, "stage": req.stage}, "SUPPORT_TRIAGE")

        if req.stage == "MANAGER_APPROVAL":
            manager_email = RequestService.get_manager_email_for_branch(db, req.employee.branch)
            EmailService.notify_stock_info_to_manager(req.employee.name, req.asset_name, manager_email, stock_msg)
        
        return RequestService._serialize_request(req)

    @staticmethod
    def review_request_by_manager(db: Session, request_id: str, payload: RequestReview, user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id).with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        if user.role != EmployeeRole.ADMIN and req.employee.branch != user.branch:
            raise HTTPException(status_code=403, detail="Managers can review only requests from their own branch.")

        if req.hr_verified is False and payload.is_approved:
            raise HTTPException(
                status_code=400,
                detail="Manager cannot approve a request that HR has explicitly rejected as NOT NEEDED.",
            )

        if req.stage != "MANAGER_APPROVAL":
            raise HTTPException(status_code=404, detail="Request not found or not in Manager stage")

        old_status = req.status
        if not payload.is_approved:
            req.status = "REJECTED"
            req.stage = "REJECTED"
        else:
            if user.role == EmployeeRole.ADMIN:
                req.status = "APPROVED_FOR_SUPPORT"
                req.stage = "READY"
            elif req.action_type in ["NEW", "REPLACE"]:
                req.status = "PENDING_ADMIN"
                req.stage = "ADMIN_APPROVAL"
            else:
                req.status = "APPROVED_FOR_SUPPORT"
                req.stage = "READY"

        db.commit()
        db.refresh(req)
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, {"status": old_status}, {"status": req.status}, "MANAGER_REVIEW")
        
        # Fetch branch support emails from DB
        support_emails = RequestService.get_emails_by_roles_in_branch(db, [EmployeeRole.SUPPORT_TEAM], req.employee.branch)
        EmailService.notify_manager_decision(req.employee.name, req.asset_name, payload.is_approved, support_emails)
        return RequestService._serialize_request(req)

    @staticmethod
    def review_request_by_admin(db: Session, request_id: str, payload: RequestReview, user: Employee):
        if user.role != EmployeeRole.ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Admins can perform this override")
        req = db.query(Request).filter(Request.request_id == request_id).with_for_update().first()
        if not req: raise HTTPException(status_code=404)
        old_status = req.status
        if not payload.is_approved:
            req.status = "REJECTED"
            req.stage = "REJECTED"
        else:
            req.status = "APPROVED_FOR_SUPPORT"
            req.stage = "READY"
        db.commit()
        db.refresh(req)
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, {"status": old_status}, {"status": req.status}, "ADMIN_OVERRIDE_REVIEW")
        return RequestService._serialize_request(req)

    @staticmethod
    def execute_asset_request(db: Session, request_id: str, provided_asset_id: str, broken_asset_id: Optional[str], user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id).with_for_update().first()
        if not req: raise HTTPException(status_code=404)
        if user.role != EmployeeRole.ADMIN and req.employee.branch != user.branch:
            raise HTTPException(status_code=403, detail="Support can execute only requests from their own branch.")
        if req.status not in ["APPROVED_FOR_SUPPORT", "READY"] and req.stage != "READY":
            raise HTTPException(status_code=400, detail="Request not actionable")

        if req.action_type in ["NEW", "REPLACE"]:
            StockService.allocate_asset(db, provided_asset_id, req.emp_id, AllocationType.PERMANENT, user, f"FULFILL_REQ_{request_id}")
            if req.action_type == "REPLACE" and broken_asset_id:
                active_trk = db.query(Tracking).filter(Tracking.asset_id == broken_asset_id, Tracking.emp_id == req.emp_id, Tracking.returned_at == None).first()
                if active_trk:
                    StockService.return_asset(db, active_trk.tracking_id, user, "REPLACEMENT_RETURN")
            req.status = "COMPLETED"
            req.stage = "COMPLETED"
        elif req.action_type == "SERVICE":
            active_trk = db.query(Tracking).filter(Tracking.asset_id == broken_asset_id, Tracking.emp_id == req.emp_id, Tracking.returned_at == None).first()
            if not active_trk:
                raise HTTPException(status_code=400, detail="Employee does not currently hold this asset")
            asset = db.query(Asset).filter(Asset.asset_id == broken_asset_id).with_for_update().first()
            asset.asset_status = AssetStatus.IN_REPAIR
            if provided_asset_id:
                StockService.allocate_asset(db, provided_asset_id, req.emp_id, AllocationType.TEMPORARY, user, f"LOANER_FOR_REQ_{request_id}")
            req.serviced_asset_id = broken_asset_id
            req.status = "WIP_SERVICE"
            req.stage = "IN_REPAIR"
        else:
            raise HTTPException(
                status_code=400,
                detail="Request has no actionable type (NEW, REPLACE, or SERVICE). Complete help desk triage first.",
            )

        db.commit()
        db.refresh(req)
        EmailService.notify_asset_assigned(req.employee.name, req.asset_name, RequestService.get_manager_email_for_branch(db, req.employee.branch))
        return req

    @staticmethod
    def resolve_service_request(db: Session, request_id: str, payload: RequestResolve, user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id, Request.status == "WIP_SERVICE").with_for_update().first()
        if not req: raise HTTPException(status_code=400, detail="No active service request found")
        if user.role != EmployeeRole.ADMIN and req.employee.branch != user.branch:
            raise HTTPException(status_code=403, detail="Support can resolve only requests from their own branch.")
        loaner_reason = f"LOANER_FOR_REQ_{request_id}"
        loaner_trk = db.query(Tracking).filter(Tracking.emp_id == req.emp_id, Tracking.movement_reason == loaner_reason, Tracking.returned_at == None).first()
        if loaner_trk:
            StockService.return_asset(db, loaner_trk.tracking_id, user, f"LOANER_RETURN_RESOLVE_{request_id}")
        repaired_asset = db.query(Asset).filter(Asset.asset_id == req.serviced_asset_id).with_for_update().first()
        if repaired_asset:
            if payload.repair_cost > 0:
                AccountService.add_maintenance_cost(db, repaired_asset.asset_id, payload.repair_cost, user, f"SERVICE_REQ_{request_id}")
            if payload.is_disposable:
                repaired_asset.asset_status = AssetStatus.RETIRED
            else:
                repaired_asset.asset_status = AssetStatus.ACTIVE
                new_trk = Tracking(asset_id=repaired_asset.asset_id, emp_id=req.emp_id, branch=repaired_asset.branch, movement_type=MovementType.ALLOCATE, allocation_type=AllocationType.PERMANENT, movement_reason="REPAIRED_ASSET_RETURNED")
                db.add(new_trk)
                db.flush()
                AuditService.log_change(db, "tracking", new_trk.tracking_id, "CREATE", user, None, {"asset_id": repaired_asset.asset_id}, "SERVICE_RESOLVE_RETURN")
        req.status = "COMPLETED"
        req.stage = "COMPLETED"
        db.commit()
        db.refresh(req)
        return req

    @staticmethod
    def try_auto_allocate_for_asset(db: Session, asset_id: str, user: Employee, trigger_reason: str = "AUTO_REALLOCATION"):
        asset = (
            db.query(Asset)
            .options(joinedload(Asset.category))
            .filter(Asset.asset_id == asset_id)
            .first()
        )
        if not asset or asset.unused <= 0 or not asset.category:
            return None

        req = (
            db.query(Request)
            .join(Request.employee)
            .filter(
                Request.stage == "READY",
                Request.status == "APPROVED_FOR_SUPPORT",
                Request.action_type.in_(["NEW", "REPLACE"]),
                Request.asset_category == asset.category.category_name,
                Employee.branch == asset.branch,
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
                Asset.branch == asset.branch,
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
        req = db.query(Request).filter(Request.request_id == request_id).with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        
        if user.role != EmployeeRole.MANAGER:
            raise HTTPException(status_code=403, detail="Only Managers can initiate a cross-branch transfer")
        if req.employee.branch != user.branch:
            raise HTTPException(status_code=403, detail="Managers can initiate transfers only for requests in their own branch.")
        
        if req.employee.branch == payload.target_branch:
            raise HTTPException(status_code=400, detail="Cannot request transfer from your own branch")

        # Find target branch stakeholders
        target_manager_email = RequestService.get_manager_email_for_branch(db, payload.target_branch)
        if not target_manager_email:
            raise HTTPException(status_code=400, detail=f"Target branch '{payload.target_branch}' has no active Manager to receive this request.")
        
        target_support_emails = RequestService.get_emails_by_roles_in_branch(db, [EmployeeRole.SUPPORT_TEAM], payload.target_branch)
        
        # Update Request Status
        old_status = req.status
        req.status = "AWAITING_TRANSFER"
        req.action_type = f"TRANSFER:{payload.target_branch}"
        transfer_tracking = None
        if req.serviced_asset_id:
            transfer_tracking = Tracking(
                asset_id=req.serviced_asset_id,
                asset_name=payload.target_asset_name,
                emp_id=req.emp_id,
                category=req.asset_category,
                branch=req.employee.branch,
                from_branch=req.employee.branch,
                to_branch=payload.target_branch,
                movement_type=MovementType.TRANSFER,
                movement_reason=f"CROSS_BRANCH_REQUEST_{request_id}",
                allocation_type=AllocationType.TEMPORARY,
                transfer_status="PENDING",
            )
            db.add(transfer_tracking)
            db.flush()
        
        db.commit()
        db.refresh(req)
        
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, 
                                {"status": old_status}, {"status": req.status, "action": req.action_type}, "CROSS_BRANCH_REQUEST")
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

        # Send Email
        recipients = [target_manager_email] + target_support_emails
        EmailService.notify_cross_branch_transfer_request(
            requester_branch=req.employee.branch,
            target_branch=payload.target_branch,
            asset_brand=payload.target_asset_brand,
            asset_name=payload.target_asset_name,
            recipients=recipients,
            reply_to_email=user.email
        )
        return req

    @staticmethod
    def get_emails_by_roles_in_branch(db: Session, roles: List[EmployeeRole], branch: str) -> List[str]:
        stakeholders = db.query(Employee.email).filter(
            Employee.branch == branch,
            Employee.role.in_(roles),
            Employee.is_active == True
        ).all()
        return [s.email for s in stakeholders]

    @staticmethod
    def get_admin_emails(db: Session) -> List[str]:
        admins = db.query(Employee.email).filter(
            Employee.role == EmployeeRole.ADMIN,
            Employee.is_active == True
        ).all()
        return [a.email for a in admins]
