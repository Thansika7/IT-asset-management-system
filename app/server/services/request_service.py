from sqlalchemy import func
from sqlalchemy.orm import Session
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

        # 2. Initialize Request: Start at HR Verification as planned
        req = Request(
            emp_id=current_user.employee_id,
            asset_name=payload.asset_name,
            asset_category=payload.asset_category,
            reason=payload.reason,
            action_type=payload.action_type,
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

        return req

    @staticmethod
    def review_request_by_hr(db: Session, request_id: str, payload: RequestHRVerify, user: Employee):
        req = db.query(Request).filter(
            Request.request_id == request_id,
            Request.stage == "HR_VERIFICATION",
        ).with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found or not in HR stage")

        old_status = req.status
        req.hr_verified = payload.is_needed
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
        return req

    @staticmethod
    def triage_asset_request(db: Session, request_id: str, payload: RequestTriage, user: Employee):
        req = db.query(Request).filter(
            Request.request_id == request_id,
            Request.stage == "HELPDESK_TRIAGE",
        ).with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found or not in Help Desk triage stage")
        
        from app.server.schema.category import Category

        requested_action = payload.action_type.strip() if payload.action_type else ""
        selected_target = None
        if ":" in requested_action:
            requested_action, selected_target = requested_action.split(":", 1)
            requested_action = requested_action.strip()
            selected_target = selected_target.strip()

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

        # Help desk triage decision is authoritative for fulfillment (overrides draft intent on the request).
        if requested_action:
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
        
        return req

    @staticmethod
    def review_request_by_manager(db: Session, request_id: str, payload: RequestReview, user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id).with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")

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
        return req

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
        return req

    @staticmethod
    def execute_asset_request(db: Session, request_id: str, provided_asset_id: str, broken_asset_id: Optional[str], user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id).with_for_update().first()
        if not req: raise HTTPException(status_code=404)
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
    def request_cross_branch_transfer(db: Session, request_id: str, payload: "RequestCrossBranchTransfer", user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id).with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")
        
        if user.role != EmployeeRole.MANAGER:
            raise HTTPException(status_code=403, detail="Only Managers can initiate a cross-branch transfer")
        
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
        
        db.commit()
        db.refresh(req)
        
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, 
                                {"status": old_status}, {"status": req.status, "action": req.action_type}, "CROSS_BRANCH_REQUEST")

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
