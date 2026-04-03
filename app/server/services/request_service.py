from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func as sql_func
from fastapi import HTTPException, status
from typing import List, Optional

from app.server.models.request import RequestCreate, RequestTriage, RequestReview, RequestResolve, RequestHRVerify
from app.server.schema.request import Request
from app.server.schema.asset import Asset, AssetStatus
from app.server.schema.tracking import Tracking, MovementType, AllocationType
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.email_service import EmailService
from app.server.services.stock_service import StockService
from app.server.services.account_service import AccountService
from app.server.services.audit_service import AuditService


class RequestService:
    PRIORITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    SLA_HOURS = {"CRITICAL": 4, "HIGH": 8, "MEDIUM": 24, "LOW": 48}

    @staticmethod
    def _serialize_request(req: Request):
        from app.server.models.request import RequestResponse
        from datetime import datetime, timedelta, timezone

        data = RequestResponse.model_validate(req)
        priority = (req.priority or "MEDIUM").upper()
        req_date = req.req_date
        if req_date:
            sla_target = req_date + timedelta(hours=RequestService.SLA_HOURS.get(priority, 24))
            data.sla_target_at = sla_target
            now = datetime.now(req_date.tzinfo) if req_date.tzinfo else datetime.now(timezone.utc).replace(tzinfo=None)
            data.sla_breached = req.stage not in {"COMPLETED", "REJECTED"} and sla_target < now
        return data

    @staticmethod
    def list_requests(
        db: Session,
        current_user: Employee,
        *,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        severity: Optional[str] = None,
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

        rows = query.all()
        if sort_by_priority:
            rows = sorted(rows, key=lambda req: RequestService.PRIORITY_ORDER.get((req.priority or "MEDIUM").upper(), 0), reverse=True)
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
                    detail="Employees cannot categorize requests. HR must set NEW, SERVICE, or REPLACE.",
                )
            if payload.priority is not None or payload.severity is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Employees cannot set priority or severity. HR must set those values.",
                )

        # 2. Initialize Request: Start at HR Verification as planned
        requested_action = payload.action_type if current_user.role in [EmployeeRole.HR, EmployeeRole.ADMIN] else None
        requested_priority = payload.priority.value if current_user.role in [EmployeeRole.HR, EmployeeRole.ADMIN] and payload.priority else "MEDIUM"
        requested_severity = payload.severity.value if current_user.role in [EmployeeRole.HR, EmployeeRole.ADMIN] and payload.severity else "MEDIUM"
        req = Request(
            emp_id=current_user.employee_id,
            asset_name=payload.asset_name,
            asset_category=payload.asset_category,
            reason=payload.reason,
            action_type=requested_action,
            priority=requested_priority,
            severity=requested_severity,
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
        if payload.is_needed and not payload.action_type:
            raise HTTPException(status_code=400, detail="HR must categorize the request as NEW, SERVICE, or REPLACE.")
        if payload.action_type:
            req.action_type = payload.action_type
        req.priority = payload.priority.value
        req.severity = payload.severity.value
        req.stage = "HELPDESK_TRIAGE"
        req.status = "PENDING_SUPPORT_TRIAGE"
        
        db.commit()
        db.refresh(req)

        AuditService.log_change(
            db,
            "requests",
            request_id,
            "UPDATE",
            user,
            {"status": old_status},
            {"status": req.status, "hr_verified": req.hr_verified},
            "HR_VERIFICATION",
        )

        # Fetch branch support emails from DB
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
        
        from app.server.schema.category import Category

        requested_action = (req.action_type or payload.action_type or "").strip()
        selected_target = None
        if ":" in requested_action:
            requested_action, selected_target = requested_action.split(":", 1)
            requested_action = requested_action.strip()
            selected_target = selected_target.strip()
        if not requested_action:
            raise HTTPException(status_code=400, detail="Request must be categorized by HR before support triage.")

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

        StockService.allocate_asset(
            db,
            asset.asset_id,
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
            {"status": req.status, "stage": req.stage, "asset_id": asset.asset_id},
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
