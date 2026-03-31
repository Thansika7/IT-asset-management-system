from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from fastapi import HTTPException, status
from typing import List, Optional

from app.server.models.request import RequestCreate, RequestTriage, RequestReview, RequestResolve, RequestHRVerify
from app.server.schema.request import Request
from app.server.schema.asset import Asset, AssetStatus
from app.server.schema.tracking import Tracking, MovementType, AllocationType
from app.server.schema.employee import Employee, EmployeeRole
from app.server.services.stock_service import StockService
from app.server.services.account_service import AccountService
from app.server.services.audit_service import AuditService
from app.server.services.email_service import EmailService

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
    def create_asset_request(db: Session, payload: RequestCreate, user: Employee):
        req=Request(
            emp_id=user.employee_id,
            asset_name=payload.asset_name,
            asset_category=payload.asset_category,
            reason=payload.reason,
            status="PENDING_HR"
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        
        AuditService.log_change(db, "requests", req.request_id, "CREATE", user, None, {
            "status": req.status,
            "asset_name": req.asset_name
        }, "USER_SUBMISSION")

        manager_email = RequestService.get_manager_email_for_branch(db, user.branch)
        EmailService.notify_request_created(user.name, payload.asset_name, manager_email)
        return req

    @staticmethod
    def review_request_by_hr(db: Session, request_id: str, payload: RequestHRVerify, user: Employee):
        req=db.query(Request).filter(Request.request_id==request_id, Request.status=="PENDING_HR").with_for_update().first()
        if not req: raise HTTPException(status_code=404, detail="Request not found or not in PENDING_HR state")
        
        old_status = req.status
        req.hr_verified = payload.is_needed
        req.status = "PENDING_SUPPORT"
        
        db.commit()
        db.refresh(req)
        
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, 
                                {"status": old_status}, {"status": req.status, "hr_verified": req.hr_verified}, "HR_VERIFICATION")

        EmailService.notify_hr_verified(req.employee.name, req.asset_name, payload.is_needed)
        return req

    @staticmethod
    def triage_asset_request(db: Session, request_id: str, payload: RequestTriage, user: Employee):
        req=db.query(Request).filter(Request.request_id==request_id, Request.status=="PENDING_SUPPORT").with_for_update().first()
        if not req: raise HTTPException(status_code=404, detail="Request not found or not in PENDING_SUPPORT state")
        
        # Check stock across branches dynamically
        from app.server.schema.category import Category
        local_stock = db.query(func.sum(Asset.unused)).join(Category).filter(
            Asset.branch == req.employee.branch,
            Category.category_name == req.asset_category
        ).scalar() or 0
        
        stock_msg = ""
        if local_stock > 0:
            stock_msg = f"Available in local branch: {req.employee.branch}"
            req.action_type = "Fulfilment: Local"
        else:
            other_stocks = RequestService.get_inventory_across_branches(db, req.asset_category)
            if not other_stocks:
                stock_msg = "Unavailable in all branches"
            else:
                branches_info = ", ".join([f"{s.branch}({s.available_quantity})" for s in other_stocks])
                stock_msg = f"Unavailable locally. Available in: {branches_info}"
        
        req.action_type = payload.action_type if payload.action_type else req.action_type
        
        if user.role == EmployeeRole.ADMIN:
            req.status = "APPROVED_FOR_SUPPORT"
        else:
            req.status="PENDING_MANAGER"
            
        db.commit()
        db.refresh(req)
        
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, 
                                {"status": "PENDING_SUPPORT"}, {"status": req.status, "action": req.action_type}, "SUPPORT_TRIAGE")
        manager_email = RequestService.get_manager_email_for_branch(db, req.employee.branch)
        EmailService.notify_stock_info_to_manager(req.employee.name, req.asset_name, manager_email, stock_msg)
        return req

    @staticmethod
    def review_request_by_manager(db: Session, request_id: str, payload: RequestReview, user: Employee):
        req=db.query(Request).filter(Request.request_id==request_id).with_for_update().first()
        if not req: raise HTTPException(status_code=404)
        
        if req.hr_verified is False and payload.is_approved:
            raise HTTPException(status_code=400, detail="Manager cannot approve a request that HR explicitly rejected as Unnecessary.")
        
        if not payload.is_approved:
            req.status="REJECTED"
        else:
            if user.role == EmployeeRole.ADMIN:
                req.status="APPROVED_FOR_SUPPORT"
            elif req.action_type in ["NEW", "REPLACE"]:
                req.status="PENDING_ADMIN"
            else:
                req.status="APPROVED_FOR_SUPPORT"
        
        db.commit()
        db.refresh(req)
        EmailService.notify_manager_decision(req.employee.name, req.asset_name, payload.is_approved)
        return req

    @staticmethod
    def review_request_by_admin(db: Session, request_id: str, payload: RequestReview, user: Employee):
        """Dedicated method for Admin Override as requested."""
        if user.role != EmployeeRole.ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Admins can perform this override")
            
        req=db.query(Request).filter(Request.request_id==request_id).with_for_update().first()
        if not req: raise HTTPException(status_code=404)
        
        old_status = req.status
        if not payload.is_approved:
            req.status="REJECTED"
        else:
            # Directly to final actionable stage
            req.status="APPROVED_FOR_SUPPORT"
            
        db.commit()
        db.refresh(req)
        AuditService.log_change(db, "requests", request_id, "UPDATE", user, 
                                {"status": old_status}, {"status": req.status}, "ADMIN_OVERRIDE_REVIEW")
        return req

    @staticmethod
    def execute_asset_request(db: Session, request_id: str, provided_asset_id: str, broken_asset_id: str | None, user: Employee):
        req=db.query(Request).filter(Request.request_id==request_id).with_for_update().first()
        if not req:
            raise HTTPException(status_code=404)
        if req.status not in ["APPROVED_FOR_SUPPORT", "READY"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Request is in state {req.status}, not executable")

        if req.action_type in ["NEW", "REPLACE"]:
            # Standard allocation (Request-First)
            StockService.allocate_asset(db, provided_asset_id, req.emp_id, AllocationType.PERMANENT, user, f"FULFILL_REQ_{request_id}")
            if req.action_type == "REPLACE" and broken_asset_id:
                # Automating return of the broken one
                active_trk = db.query(Tracking).filter(Tracking.asset_id==broken_asset_id, Tracking.emp_id==req.emp_id, Tracking.returned_at==None).first()
                if active_trk:
                    StockService.return_asset(db, active_trk.tracking_id, user, "REPLACMENT_RETURN")
            req.status = "COMPLETED"
            
            manager_email = RequestService.get_manager_email_for_branch(db, req.employee.branch)
            EmailService.notify_asset_assigned(req.employee.name, req.asset_name, manager_email)

        elif req.action_type == "SERVICE":
            # 1. Identify active tracking for the broken asset
            active_trk = db.query(Tracking).filter(Tracking.asset_id==broken_asset_id, Tracking.emp_id==req.emp_id, Tracking.returned_at==None).first()
            if not active_trk:
                raise HTTPException(status_code=400, detail="Employee does not currently hold this asset")

            # 2. Return original asset from user (increments unused)
            StockService.return_asset(db, active_trk.tracking_id, user, "SENT_FOR_REPAIR")

            # 3. Mark original asset as IN_REPAIR and lock it (decrement unused back)
            asset = db.query(Asset).filter(Asset.asset_id==broken_asset_id).with_for_update().first()
            asset.asset_status = AssetStatus.IN_REPAIR
            asset.unused -= 1
            
            # 4. Provided asset is a LOANER
            if provided_asset_id:
                StockService.allocate_asset(db, provided_asset_id, req.emp_id, AllocationType.TEMPORARY, user, f"LOANER_FOR_REQ_{request_id}")
            
            req.serviced_asset_id = broken_asset_id
            req.status = "WIP_SERVICE"
            
        db.commit()
        db.refresh(req)
        return req

    @staticmethod
    def resolve_service_request(db: Session, request_id: str, payload: RequestResolve, user: Employee):
        req=db.query(Request).filter(Request.request_id==request_id, Request.status=="WIP_SERVICE").with_for_update().first()
        if not req: raise HTTPException(status_code=400, detail="No active service request found for this ID")

        # 1. Find the TEMPORARY loaner specifically assigned for this request
        loaner_reason = f"LOANER_FOR_REQ_{request_id}"
        loaner_trk = db.query(Tracking).filter(
            Tracking.emp_id == req.emp_id,
            Tracking.movement_reason == loaner_reason,
            Tracking.returned_at == None
        ).first()

        # 2. Return the loaner to stock (increments unused, decrements used)
        if loaner_trk:
            StockService.return_asset(db, loaner_trk.tracking_id, user, f"LOANER_RETURN_RESOLVE_{request_id}")


        # 3. Record the maintenance cost using the stored asset_id
        if not req.serviced_asset_id:
             raise HTTPException(status_code=400, detail="Request has no linked asset ID for service")
             
        repaired_asset = db.query(Asset).filter(Asset.asset_id == req.serviced_asset_id).with_for_update().first()
        
        if repaired_asset:
            if payload.repair_cost > 0:
                AccountService.add_maintenance_cost(db, repaired_asset.asset_id, payload.repair_cost, user, f"SERVICE_REQ_{request_id}")
            
            if payload.is_disposable:
                repaired_asset.asset_status = AssetStatus.RETIRED
                # If they held it, mark it returned from repair but immediately retired
            else:
                repaired_asset.asset_status = AssetStatus.ACTIVE
                repaired_asset.used += 1 # Restore used count manually
                # Return to employee: Create tracking record
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
        db.commit()
        db.refresh(req)
        return req
