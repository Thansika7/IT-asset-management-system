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
            func.sum(Asset.unused).label("available_quantity")
        ).join(Category).filter(Category.category_name == category_name)
        
        return query.group_by(Asset.branch).all()

    @staticmethod
    def get_manager_email_for_branch(db: Session, branch: str) -> str:
        manager = db.query(Employee).filter(
            Employee.branch == branch,
            Employee.role == EmployeeRole.MANAGER,
            Employee.is_active == True
        ).first()
        return manager.email if manager else None

    @staticmethod
    def create_asset_request(db: Session, payload: RequestCreate, current_user: Employee):
        req = Request(
            emp_id=current_user.employee_id,
            asset_name=payload.asset_name,
            asset_category=payload.asset_category,
            reason=payload.reason,
            status="PENDING_HR",
            stage="HR_VERIFICATION"
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        
        # Log the change
        AuditService.log_change(db, "requests", req.request_id, "CREATE", current_user, None, {
            "status": req.status,
            "asset_name": req.asset_name
        }, "USER_SUBMISSION")

        # Notify Help Desk, HR, and Manager
        manager_email = RequestService.get_manager_email_for_branch(db, current_user.branch)
        EmailService.notify_request_created(current_user.name, payload.asset_name, manager_email)

        return req

    @staticmethod
    def review_request_by_hr(db: Session, request_id: str, payload: RequestHRVerify, user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "HR_VERIFICATION").with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found or not in HR stage")
        
        old_status = req.status
        req.hr_verified = payload.is_needed
        req.stage = "HELPDESK_TRIAGE"
        req.status = "PENDING_SUPPORT"
        
        db.commit()
        db.refresh(req)
        
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, 
                                {"status": old_status}, {"status": req.status, "hr_verified": req.hr_verified}, "HR_VERIFICATION")

        # Notify Help Desk that they can now triage
        EmailService.notify_hr_verified(req.employee.name, req.asset_name, payload.is_needed)
        
        return req

    @staticmethod
    def triage_asset_request(db: Session, request_id: str, payload: RequestTriage, user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "HELPDESK_TRIAGE").with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found or not in Help Desk triage stage")
        
        # Check if asset is available in the current branch
        from app.server.schema.category import Category
        local_stock = db.query(sql_func.sum(Asset.unused)).join(Category).filter(
            Asset.branch == req.employee.branch,
            Category.category_name == req.asset_category
        ).scalar() or 0
        
        stock_msg = ""
        if local_stock > 0:
            req.status = f"Available in local branch: {req.employee.branch}"
            stock_msg = req.status
            req.action_type = "Fulfilment: Local"
        else:
            # Check other branches
            other_stocks = RequestService.get_inventory_across_branches(db, req.asset_category)
            if not other_stocks:
                req.status = "Unavailable in all branches"
                stock_msg = req.status
            else:
                branches_info = ", ".join([f"{s.branch}({s.available_quantity})" for s in other_stocks])
                req.status = f"Unavailable locally. Available in: {branches_info}"
                stock_msg = req.status
                
                if ":" in payload.action_type:
                    action, target = payload.action_type.split(":", 1)
                    req.action_type = action
                    req.status += f" (Selected: {target})"
        
        if not req.action_type and payload.action_type:
             req.action_type = payload.action_type

        # Admin Override: If Admin triages, it can skip manager review
        if user.role == EmployeeRole.ADMIN:
            req.status = "APPROVED_FOR_SUPPORT"
            req.stage = "READY"
        else:
            req.status = "PENDING_MANAGER"
            req.stage = "MANAGER_APPROVAL"

        db.commit()
        db.refresh(req)
        
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, 
                                {"status": "PENDING_SUPPORT"}, {"status": req.status, "action": req.action_type}, "SUPPORT_TRIAGE")

        # Notify Manager of stock availability
        manager_email = RequestService.get_manager_email_for_branch(db, req.employee.branch)
        EmailService.notify_stock_info_to_manager(req.employee.name, req.asset_name, manager_email, stock_msg)
        
        return req

    @staticmethod
    def review_request_by_manager(db: Session, request_id: str, payload: RequestReview, user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "MANAGER_APPROVAL").with_for_update().first()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found or not in Manager stage")
        
        # Enforcement: if HR verified as NOT needed, manager cannot approve
        if not req.hr_verified and payload.is_approved:
             raise HTTPException(status_code=400, detail="Manager cannot approve a request that HR has verified as NOT NEEDED.")

        old_status = req.status
        if not payload.is_approved:
            req.status = "REJECTED"
            req.stage = "REJECTED"
        else:
            # High-level override: if an Admin is reviewing as a manager
            if user.role == EmployeeRole.ADMIN:
                req.status = "APPROVED_FOR_SUPPORT"
                req.stage = "READY"
            elif req.action_type in ["NEW", "REPLACE"]:
                req.status = "PENDING_ADMIN"
                req.stage = "ADMIN_APPROVAL" # If admin review is needed
            else:
                req.status = "APPROVED_FOR_SUPPORT"
                req.stage = "READY"
        
        db.commit()
        db.refresh(req)
        
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, 
                                {"status": old_status}, {"status": req.status}, "MANAGER_REVIEW")

        EmailService.notify_manager_decision(req.employee.name, req.asset_name, payload.is_approved)
            
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
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, 
                                {"status": old_status}, {"status": req.status}, "ADMIN_OVERRIDE_REVIEW")
        return req

    @staticmethod
    def execute_asset_request(db: Session, request_id: str, provided_asset_id: str, broken_asset_id: Optional[str], user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "READY").with_for_update().first()
        if not req:
            raise HTTPException(status_code=400, detail="Invalid request state or not approved by Manager")

        if req.action_type in ["NEW", "REPLACE", "TRANSFER"]:
            StockService.allocate_asset(db, provided_asset_id, req.emp_id, AllocationType.PERMANENT, user, f"FULFILL_REQ_{request_id}")
            if req.action_type == "REPLACE" and broken_asset_id:
                # Automating return of the broken one
                active_trk = db.query(Tracking).filter(Tracking.asset_id == broken_asset_id, Tracking.emp_id == req.emp_id, Tracking.returned_at == None).first()
                if active_trk:
                    StockService.return_asset(db, active_trk.tracking_id, user, "REPLACEMENT_RETURN")
            
            req.status = "Assigned"
            req.stage = "COMPLETED"

        elif req.action_type == "SERVICE":
            # 1. Identify active tracking for the broken asset
            active_trk = db.query(Tracking).filter(Tracking.asset_id == broken_asset_id, Tracking.emp_id == req.emp_id, Tracking.returned_at == None).first()
            if not active_trk:
                raise HTTPException(status_code=400, detail="Employee does not currently hold this asset")

            # 2. Mark original asset as IN_REPAIR
            asset = db.query(Asset).filter(Asset.asset_id == broken_asset_id).with_for_update().first()
            asset.asset_status = AssetStatus.IN_REPAIR
            
            # 3. Provided asset is a LOANER
            if provided_asset_id:
                StockService.allocate_asset(db, provided_asset_id, req.emp_id, AllocationType.TEMPORARY, user, f"LOANER_FOR_REQ_{request_id}")
            
            req.serviced_asset_id = broken_asset_id
            req.status = "WIP_SERVICE" 
            req.stage = "IN_REPAIR"
            
        db.commit()
        db.refresh(req)

        # Notify Manager of assignment completion
        manager_email = RequestService.get_manager_email_for_branch(db, req.employee.branch)
        EmailService.notify_asset_assigned(req.employee.name, req.asset_name, manager_email)

        return req

    @staticmethod
    def resolve_service_request(db: Session, request_id: str, payload: RequestResolve, user: Employee):
        req = db.query(Request).filter(Request.request_id == request_id, Request.status == "WIP_SERVICE").with_for_update().first()
        if not req: raise HTTPException(status_code=400, detail="No active service request found for this ID")

        # 1. Find the TEMPORARY loaner specifically assigned for this request
        loaner_reason = f"LOANER_FOR_REQ_{request_id}"
        loaner_trk = db.query(Tracking).filter(
            Tracking.emp_id == req.emp_id,
            Tracking.movement_reason == loaner_reason,
            Tracking.returned_at == None
        ).first()

        # 2. Return the loaner to stock
        if loaner_trk:
            StockService.return_asset(db, loaner_trk.tracking_id, user, f"LOANER_RETURN_RESOLVE_{request_id}")

        # 3. Record maintenance and return original
        if not req.serviced_asset_id:
             raise HTTPException(status_code=400, detail="Request has no linked asset ID for service")
             
        repaired_asset = db.query(Asset).filter(Asset.asset_id == req.serviced_asset_id).with_for_update().first()
        
        if repaired_asset:
            if payload.repair_cost > 0:
                AccountService.add_maintenance_cost(db, repaired_asset.asset_id, payload.repair_cost, user, f"SERVICE_REQ_{request_id}")
            
            if payload.is_disposable:
                repaired_asset.asset_status = AssetStatus.RETIRED
            else:
                repaired_asset.asset_status = AssetStatus.ACTIVE
                # Return to employee
                new_trk = Tracking(
                    asset_id=repaired_asset.asset_id,
                    emp_id=req.emp_id,
                    branch=repaired_asset.branch,
                    movement_type=MovementType.ALLOCATE,
                    allocation_type=AllocationType.PERMANENT,
                    movement_reason="REPAIRED_ASSET_RETURNED"
                )
                db.add(new_trk)
                db.flush()
                AuditService.log_change(db, "tracking", new_trk.tracking_id, "CREATE", user, None, {"asset_id": repaired_asset.asset_id}, "SERVICE_RESOLVE_RETURN")

        req.status = "COMPLETED"
from app.server.models.request import RequestCreate, RequestTriage, RequestReview
from app.server.services.email_service import EmailService
from app.server.schema.employee import EmployeeRole

def get_inventory_across_branches(db: Session, category_name: str):
    from app.server.schema.category import Category
    query = db.query(
        Asset.branch,
        func.sum(Asset.unused).label("available_quantity")
    ).join(Category).filter(Category.category_name == category_name)
    
    return query.group_by(Asset.branch).all()

def get_manager_email_for_branch(db: Session, branch: str) -> str:
    manager = db.query(Employee).filter(
        Employee.branch == branch,
        Employee.role == EmployeeRole.MANAGER,
        Employee.is_active == True
    ).first()
    return manager.email if manager else None

def create_asset_request(db: Session, payload: RequestCreate, current_user: Employee):
    req = Request(
        emp_id=current_user.employee_id,
        asset_name=payload.asset_name,
        asset_category=payload.asset_category,
        reason=payload.reason,
        status="Pending",
        stage="HR_VERIFICATION"
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    
    # Notify Help Desk, HR, and Manager
    manager_email = get_manager_email_for_branch(db, current_user.branch)
    EmailService.notify_request_created(current_user.name, payload.asset_name, manager_email)

    return req

def review_request_by_hr(db: Session, request_id: str, payload: RequestHRVerify):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "HR_VERIFICATION").first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found or not in HR stage")
    
    req.hr_verified = payload.is_needed
    req.stage = "HELPDESK_TRIAGE"
    req.status = "HR Verified: " + ("Needed" if payload.is_needed else "Not Needed")
    
    db.commit()
    db.refresh(req)
    
    # Notify Help Desk that they can now triage
    EmailService.notify_hr_verified(req.employee.name, req.asset_name, payload.is_needed)
    
    return req

def triage_asset_request(db: Session, request_id: str, payload: RequestTriage):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "HELPDESK_TRIAGE").first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found or not in Help Desk triage stage")
    
    # Check if asset is available in the current branch
    from app.server.schema.category import Category
    local_stock = db.query(func.sum(Asset.unused)).join(Category).filter(
        Asset.branch == req.employee.branch,
        Category.category_name == req.asset_category
    ).scalar() or 0
    
    stock_msg = ""
    if local_stock > 0:
        req.status = f"Available in local branch: {req.employee.branch}"
        stock_msg = req.status
        req.action_type = "Fulfilment: Local"
    else:
        # Check other branches
        other_stocks = get_inventory_across_branches(db, req.asset_category)
        if not other_stocks:
            req.status = "Unavailable in all branches"
            stock_msg = req.status
        else:
            branches_info = ", ".join([f"{s.branch}({s.available_quantity})" for s in other_stocks])
            req.status = f"Unavailable locally. Available in: {branches_info}"
            stock_msg = req.status
            
            if ":" in payload.action_type:
                action, target = payload.action_type.split(":", 1)
                req.action_type = action
                req.status += f" (Selected: {target})"
    
    if not req.action_type and payload.action_type:
         req.action_type = payload.action_type

    req.stage = "MANAGER_APPROVAL"
    db.commit()
    db.refresh(req)
    
    # Notify Manager of stock availability
    manager_email = get_manager_email_for_branch(db, req.employee.branch)
    EmailService.notify_stock_info_to_manager(req.employee.name, req.asset_name, manager_email, stock_msg)
    
    return req

def review_request_by_manager(db: Session, request_id: str, payload: RequestReview):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "MANAGER_APPROVAL").first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found or not in Manager stage")
    
    # Enforcement: if HR verified as NOT needed, manager cannot approve (or should stay denied)
    if not req.hr_verified and payload.is_approved:
         raise HTTPException(status_code=400, detail="Manager cannot approve a request that HR has verified as NOT NEEDED.")

    if payload.is_approved:
        req.stage = "READY"
        req.status = "Approved"
    else:
        req.status = "Denied"
        req.stage = "REJECTED"
    
    db.commit()
    db.refresh(req)
    
    EmailService.notify_manager_decision(req.employee.name, req.asset_name, payload.is_approved)
        
    return req

def execute_asset_request(db: Session, request_id: str, provided_asset_id: str, broken_asset_id: str = None):
    req = db.query(Request).filter(Request.request_id == request_id, Request.stage == "READY").first()
    if not req:
        raise HTTPException(status_code=400, detail="Invalid request state or not approved by Manager")
    
    # Parse target branch from status
    target_branch = req.employee.branch
    if "Transfer from: " in req.status:
        target_branch = req.status.replace("Transfer from: ", "")
    
    asset = db.query(Asset).filter(
        Asset.asset_id == provided_asset_id,
        Asset.branch == target_branch
    ).with_for_update().first()
    
    if not asset or asset.unused <= 0:
        raise HTTPException(status_code=400, detail=f"Target asset unavailable in branch {target_branch}")
    
    if req.action_type in ["NEW", "REPLACE", "TRANSFER"]:
        asset.unused -= 1
        asset.used += 1
        if asset.unused == 0:
            asset.asset_status = AssetStatus.ALLOCATED
        
        source_branch = req.employee.branch
        trk = Tracking(
            asset_id=asset.asset_id, emp_id=req.emp_id, branch=source_branch,
            from_branch=target_branch if target_branch != source_branch else None,
            to_branch=source_branch if target_branch != source_branch else None,
            movement_type=MovementType.ALLOCATE if req.action_type == "NEW" else MovementType.REPLACE,
            allocation_type=AllocationType.PERMANENT, movement_reason=req.reason
        )
        if target_branch != source_branch:
            asset.branch = source_branch
            
        db.add(trk)
        
        if req.action_type == "REPLACE" and broken_asset_id:
            broken = db.query(Asset).filter(Asset.asset_id == broken_asset_id).with_for_update().first()
            if broken:
                broken.asset_status = AssetStatus.RETIRED
            
    req.status = "Assigned"
    req.stage = "COMPLETED"
    db.commit()
    db.refresh(req)
    
    # Notify Manager of assignment completion
    manager_email = get_manager_email_for_branch(db, req.employee.branch)
    EmailService.notify_asset_assigned(req.employee.name, req.asset_name, manager_email)
    
    return {"status": "success", "executed_action": req.action_type}
