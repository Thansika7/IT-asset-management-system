from fastapi import APIRouter, Depends, HTTPException
import logging
from sqlalchemy.orm import Session
from sqlalchemy import case, func, or_, and_
from typing import List, Optional
from uuid import uuid4

from app.server.database.database import get_db
from app.server.auth.service import get_current_user
from app.server.models.stock import AssetCreate, StockAdd, StockResponse, AllocateRequest, ReturnRequest, StockListResponse, AssetInstanceListResponse, InventorySnapshot
from app.server.schema.asset import Asset, AssetInstance, AssetStatus
from app.server.schema.category import Category, SubCategory, AssetBehavior
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.schema.organization import Branch, BranchStatus
from app.server.schema.employee import Employee, EmployeeRole
from app.server.middlewares.auth import require_roles, RequirePermission
from app.server.services.stock_service import StockService
from app.server.services.lifecycle_service import LifecycleService
from app.server.services.cron_service import CronService
from app.server.database.tenant import apply_tenant_filter

# Tagging as internal/manual-override to prioritize the automated Request lifecycle
router=APIRouter(prefix="/stock", tags=["stock_inventory_manual"])
logger = logging.getLogger(__name__)

@router.get("/", response_model=StockListResponse)
def list_inventory_status(
    search: Optional[str]=None,
    category_id: Optional[str]=None,
    branch_id: Optional[str]=None,
    organization_id: Optional[str]=None,
    status: Optional[str]=None,
    brand: Optional[str]=None,
    model: Optional[str]=None,
    page: int = 1,
    per_page: int = 20,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    """
    View full inventory snapshot across branches (scoped by organization for non super-admins).
    
    Returns dynamically calculated inventory from AssetInstance statuses.
    Do NOT trust legacy static counters (total_quantity, used, unused).
    """
    query = db.query(Asset)
    
    # Standard tenant scoping
    from app.server.database.tenant import apply_tenant_filter
    query = apply_tenant_filter(query, current_user, Asset)
    
    if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM] and current_user.branch_id:
        query = query.filter(Asset.branch_id == current_user.branch_id)
        
    if branch_id:
        query = query.filter(Asset.branch_id == branch_id)
    if organization_id and current_user.role == EmployeeRole.SUPER_ADMIN:
        query = query.filter(Asset.organization_id == organization_id)
    if category_id:
        query = query.filter(Asset.category_id == category_id)
    if brand:
        query = query.filter(Asset.brand == brand)
    if model:
        query = query.filter(Asset.model == model)
    if status:
        query = query.filter(Asset.asset_status == status.upper())

    if search:
        search_filter = f"%{search}%"
        query = query.join(Category, isouter=True).filter(
            or_(
                Asset.name.ilike(search_filter),
                Asset.brand.ilike(search_filter),
                Asset.model.ilike(search_filter),
                Category.category_name.ilike(search_filter)
            )
        )
        
    total = query.count()
    items = query.order_by(Asset.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    asset_ids = [asset.asset_id for asset in items]
    inventory_map = {aid: {"available": 0, "assigned": 0, "in_repair": 0, "not_usable": 0, "retired": 0, "total": 0} for aid in asset_ids}
    if asset_ids:
        snapshot_rows = (
            db.query(
                AssetInstance.asset_id.label("asset_id"),
                func.sum(case((AssetInstance.status == AssetStatus.AVAILABLE, 1), else_=0)).label("available"),
                func.sum(case((AssetInstance.status == AssetStatus.ASSIGNED, 1), else_=0)).label("assigned"),
                func.sum(case((AssetInstance.status == AssetStatus.IN_REPAIR, 1), else_=0)).label("in_repair"),
                func.sum(case((AssetInstance.status == AssetStatus.NOT_USABLE, 1), else_=0)).label("not_usable"),
                func.sum(case((AssetInstance.status == AssetStatus.RETIRED, 1), else_=0)).label("retired"),
                func.count(AssetInstance.instance_id).label("instance_count"),
            )
            .filter(AssetInstance.asset_id.in_(asset_ids))
            .group_by(AssetInstance.asset_id)
            .all()
        )
        for row in snapshot_rows:
            retired = int(row.retired or 0)
            total_active = max(int(row.instance_count or 0) - retired, 0)
            inventory_map[row.asset_id] = {
                "available": int(row.available or 0),
                "assigned": int(row.assigned or 0),
                "in_repair": int(row.in_repair or 0),
                "not_usable": int(row.not_usable or 0),
                "retired": retired,
                "total": total_active,
            }
    
    # Enrich each asset with dynamic inventory calculation
    enriched_items = []
    for asset in items:
        inventory_snapshot = inventory_map.get(asset.asset_id, {"available": 0, "assigned": 0, "in_repair": 0, "not_usable": 0, "retired": 0, "total": 0})
        
        item_dict = {
            "asset_id": asset.asset_id,
            "name": asset.name,
            "brand": asset.brand,
            "model": asset.model,
            # Legacy fields (deprecated, use 'inventory' instead)
            "total_quantity": asset.total_quantity,
            "used": asset.used,
            "unused": asset.unused,
            # New DYNAMIC inventory (source of truth)
            "inventory": InventorySnapshot(
                total=inventory_snapshot["total"],
                available=inventory_snapshot["available"],
                assigned=inventory_snapshot["assigned"],
                in_repair=inventory_snapshot["in_repair"],
                not_usable=inventory_snapshot["not_usable"],
                retired=inventory_snapshot["retired"],
            ),
            "instances": []  # Omit full instance list for list view to save bandwidth
        }
        enriched_items.append(item_dict)
    
    return {
        "items": enriched_items,
        "total": total,
        "page": page,
        "per_page": per_page
    }

@router.get("/instances", response_model=AssetInstanceListResponse)
def list_asset_instances(
    search: Optional[str]=None,
    asset_id: Optional[str]=None, # Filter by Model
    branch_id: Optional[str]=None,
    status: Optional[str]=None,
    page: int = 1,
    per_page: int = 20,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    """List specific physical asset instances."""
    query = db.query(AssetInstance)
    
    from app.server.database.tenant import apply_tenant_filter
    query = apply_tenant_filter(query, current_user, AssetInstance)
    
    if current_user.role in [EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM] and current_user.branch_id:
        query = query.filter(AssetInstance.branch_id == current_user.branch_id)

    if asset_id:
        query = query.filter(AssetInstance.asset_id == asset_id)
    if branch_id:
        query = query.filter(AssetInstance.branch_id == branch_id)
    if status:
        query = query.filter(AssetInstance.status == status.upper())
        
    if search:
        search_filter = f"%{search}%"
        query = query.join(Asset).join(Category, isouter=True).filter(
            or_(
                AssetInstance.serial_number.ilike(search_filter),
                AssetInstance.asset_tag.ilike(search_filter),
                AssetInstance.instance_id.ilike(search_filter),
                Asset.name.ilike(search_filter),
                Asset.brand.ilike(search_filter),
                Category.category_name.ilike(search_filter)
            )
        )
        
    total = query.count()
    items = query.order_by(AssetInstance.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page
    }


@router.post("/", response_model=StockResponse, status_code=201)
def create_asset_entry(
    payload: AssetCreate, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    """Register a new hardware item in the system's catalog."""
    
    # Start transaction
    try:
        resolved_org_id = payload.organization_id or current_user.organization_id
        resolved_branch_id = payload.branch_id
        if resolved_branch_id:
            branch_obj = apply_tenant_filter(db.query(Branch), current_user, Branch).filter(Branch.branch_id == resolved_branch_id).first()
            if not branch_obj:
                raise HTTPException(status_code=400, detail="Invalid branch_id")
            resolved_org_id = branch_obj.organization_id

        if current_user.role != EmployeeRole.SUPER_ADMIN:
            resolved_org_id = current_user.organization_id
            if resolved_branch_id and current_user.branch_id and resolved_branch_id != current_user.branch_id:
                raise HTTPException(status_code=403, detail="Support can create assets only in their own branch")
        elif not resolved_org_id:
            raise HTTPException(status_code=400, detail="organization_id is required for asset creation")

        spec_map = {}
        for spec in payload.specifications:
            if spec.attribute_name:
                spec_map[spec.attribute_name.strip().lower()] = spec.value.strip()

        asset_brand = payload.brand or spec_map.get("brand")
        asset_model = payload.model or spec_map.get("model")

        cat = None
        if payload.category_id:
            cat = apply_tenant_filter(
                db.query(Category),
                current_user,
                Category,
                allow_cross_branch=True,
            ).filter(Category.category_id == payload.category_id).first()
            if not cat and current_user.role != EmployeeRole.SUPER_ADMIN:
                cat = db.query(Category).filter(
                    Category.category_id == payload.category_id,
                    or_(Category.organization_id == resolved_org_id, Category.organization_id.is_(None)),
                ).first()
            if not cat:
                raise HTTPException(status_code=400, detail="Invalid category_id")
            if cat.organization_id and resolved_org_id and cat.organization_id != resolved_org_id:
                raise HTTPException(status_code=400, detail="category_id does not belong to your organization")
        elif payload.category_name:
            normalized_category_name = payload.category_name.strip()
            cat = apply_tenant_filter(
                db.query(Category),
                current_user,
                Category,
                allow_cross_branch=True,
            ).filter(func.lower(Category.category_name) == normalized_category_name.lower()).first()
            if not cat:
                # Fallback for globally seeded categories (organization_id is NULL).
                cat = db.query(Category).filter(
                    func.lower(Category.category_name) == normalized_category_name.lower(),
                    Category.organization_id.is_(None),
                ).first()
            if not cat:
                cat = Category(
                    category_name=normalized_category_name,
                    asset_behavior=(payload.asset_behavior or AssetBehavior.INSTANCE_BASED.value),
                    organization_id=resolved_org_id,
                    branch_id=resolved_branch_id or current_user.branch_id,
                )
                db.add(cat)
                db.flush()
            elif payload.asset_behavior and cat.asset_behavior != payload.asset_behavior:
                cat.asset_behavior = payload.asset_behavior
        else:
            raise HTTPException(status_code=400, detail="Either category_id or category_name is required")

        sub_category = None
        if payload.sub_category_id:
            sub_category = apply_tenant_filter(
                db.query(SubCategory),
                current_user,
                SubCategory,
                allow_cross_branch=True,
            ).filter(
                SubCategory.sub_category_id == payload.sub_category_id,
                SubCategory.category_id == cat.category_id,
            ).first()
            if not sub_category and current_user.role != EmployeeRole.SUPER_ADMIN:
                sub_category = db.query(SubCategory).filter(
                    SubCategory.sub_category_id == payload.sub_category_id,
                    SubCategory.category_id == cat.category_id,
                    or_(SubCategory.organization_id == resolved_org_id, SubCategory.organization_id.is_(None)),
                ).first()
            if not sub_category:
                raise HTTPException(status_code=400, detail="Invalid sub_category_id for selected category")
            if sub_category.organization_id and resolved_org_id and sub_category.organization_id != resolved_org_id:
                raise HTTPException(status_code=400, detail="sub_category_id does not belong to your organization")
        elif payload.sub_category_name:
            normalized_sub_category_name = payload.sub_category_name.strip()
            sub_category = apply_tenant_filter(
                db.query(SubCategory),
                current_user,
                SubCategory,
                allow_cross_branch=True,
            ).filter(
                SubCategory.category_id == cat.category_id,
                func.lower(SubCategory.sub_category_name) == normalized_sub_category_name.lower(),
            ).first()
            if not sub_category:
                # Fallback for globally seeded sub-categories linked to global categories.
                sub_category = db.query(SubCategory).filter(
                    SubCategory.category_id == cat.category_id,
                    func.lower(SubCategory.sub_category_name) == normalized_sub_category_name.lower(),
                    or_(SubCategory.organization_id == resolved_org_id, SubCategory.organization_id.is_(None)),
                ).first()
            if not sub_category:
                sub_category = SubCategory(
                    category_id=cat.category_id,
                    sub_category_name=normalized_sub_category_name,
                    organization_id=resolved_org_id,
                    branch_id=resolved_branch_id or current_user.branch_id,
                )
                db.add(sub_category)
                db.flush()

        if not resolved_branch_id and current_user.role == EmployeeRole.SUPPORT_TEAM:
            resolved_branch_id = current_user.branch_id

        # Create Asset with vendor information
        unit_purchase_cost = payload.purchase_cost
        total_purchase_cost = (unit_purchase_cost or 0.0) * max(payload.total_quantity, 0)
        asset_kwargs = {
            "name": payload.name,
            "category_id": cat.category_id,
            "asset_behavior": payload.asset_behavior or cat.asset_behavior,
            "asset_usage_type": payload.asset_usage_type or "INDIVIDUAL",
            "sub_category_id": sub_category.sub_category_id if sub_category else None,
            "organization_id": resolved_org_id,
            "branch_id": resolved_branch_id,
            "brand": asset_brand,
            "model": asset_model,
            "purchased_date": payload.purchased_date,
            "purchase_cost": unit_purchase_cost,
            "total_purchase_cost": total_purchase_cost,
            "salvage_value": payload.salvage_value,
            "vendor_name": payload.vendor_name,
            "vendor_contact": payload.vendor_contact,
            "invoice_number": payload.invoice_number,
            "useful_life_years": payload.useful_life_years,
            "total_quantity": payload.total_quantity,
            "unused": payload.unused,
            "used": max(payload.total_quantity - payload.unused, 0),
        }
        if payload.asset_id:
            asset_kwargs["asset_id"] = payload.asset_id

        asset = Asset(**asset_kwargs)
        db.add(asset)
        db.flush()

        # Process specifications
        if payload.specifications:
            for spec in payload.specifications:
                attribute = None
                if spec.attribute_id:
                    attribute_query = apply_tenant_filter(
                        db.query(AssetAttribute),
                        current_user,
                        AssetAttribute,
                        allow_cross_branch=True,
                    )
                    attribute = attribute_query.filter(AssetAttribute.attribute_id == spec.attribute_id).first()
                    if not attribute:
                        raise HTTPException(status_code=400, detail=f"Invalid attribute_id: {spec.attribute_id}")
                else:
                    if not spec.attribute_name:
                        raise HTTPException(status_code=400, detail="attribute_name is required when attribute_id is not provided")
                    if not sub_category:
                        raise HTTPException(status_code=400, detail="Sub-category is required to create a new attribute")

                    existing_attribute = apply_tenant_filter(
                        db.query(AssetAttribute),
                        current_user,
                        AssetAttribute,
                        allow_cross_branch=True,
                    ).filter(
                        AssetAttribute.sub_category_id == sub_category.sub_category_id,
                        AssetAttribute.attribute_name.ilike(spec.attribute_name),
                    ).first()
                    if existing_attribute:
                        attribute = existing_attribute
                    else:
                        attribute = AssetAttribute(
                            organization_id=resolved_org_id,
                            branch_id=resolved_branch_id,
                            sub_category_id=sub_category.sub_category_id,
                            attribute_name=spec.attribute_name,
                            data_type=spec.data_type or "text",
                            is_required=spec.is_required,
                        )
                        db.add(attribute)
                        db.flush()

                attr_value = AssetAttributeValue(
                    organization_id=resolved_org_id,
                    branch_id=resolved_branch_id,
                    asset_id=asset.asset_id,
                    attribute_id=attribute.attribute_id,
                    value=spec.value,
                )
                db.add(attr_value)
        
        db.flush()
        
        # Unified model: create AssetInstances for any behavior when quantity is provided.
        if payload.total_quantity > 0:
            behavior = payload.asset_behavior or cat.asset_behavior
            created_instances = 0
            for i in range(payload.total_quantity):
                # Use UUID-based instance ID for concurrency safety
                instance = AssetInstance(
                    instance_id=f"INS-{uuid4().hex[:12].upper()}",
                    asset_id=asset.asset_id,
                    organization_id=resolved_org_id,
                    branch_id=resolved_branch_id,
                    # Vendor data per instance
                    vendor_name=payload.vendor_name,
                    vendor_contact=payload.vendor_contact,
                    invoice_number=payload.invoice_number,
                    # Purchase data per instance
                    purchase_date=payload.purchased_date,
                    purchase_cost=payload.purchase_cost,
                    warranty_expiry=payload.warranty_expiry or payload.expiry_date,
                    expiry_date=payload.expiry_date,
                    subscription_term=payload.subscription_term,
                    license_key=(f"LIC-{uuid4().hex[:12].upper()}" if behavior == AssetBehavior.LICENSE_BASED.value else None),
                    instance_metadata=(payload.instance_metadata or None),
                    status=AssetStatus.AVAILABLE,
                )
                db.add(instance)
                created_instances += 1
            
            db.flush()
            
            # Verify instances were created
            instance_count = db.query(AssetInstance).filter(
                AssetInstance.asset_id == asset.asset_id
            ).count()
            
            if instance_count != payload.total_quantity:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Failed to create instances: created {instance_count}, expected {payload.total_quantity}"
                )

        db.commit()
        db.refresh(asset)
        
        # Return asset (will be converted by StockResponse model)
        return asset
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Asset creation failed: {str(e)}")

@router.post("/add", response_model=StockResponse)
def add_new_stock(
    payload: StockAdd, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    """
    Restock an asset and optionally record procurement data.
    
    Returns asset with dynamically calculated inventory.
    """
    asset = StockService.add_stock(
        db, payload.asset_id, payload.quantity, current_user,
        cost=payload.cost, vendor_name=payload.vendor_name,
        invoice_number=payload.invoice_number,
        instances=payload.instances
    )
    db.commit()
    db.refresh(asset)
    
    # Return with dynamic inventory calculation
    inventory_snapshot = StockService.get_inventory(db, asset.asset_id)
    
    return {
        "asset_id": asset.asset_id,
        "name": asset.name,
        "brand": asset.brand,
        "model": asset.model,
        "total_quantity": asset.total_quantity,
        "used": asset.used,
        "unused": asset.unused,
        "inventory": InventorySnapshot.from_service(inventory_snapshot),
        "instances": []
    }


@router.delete("/{asset_id}")
def delete_asset_entry(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN)),
):
    """Delete an asset model from inventory if it has no active/history links."""
    StockService.delete_asset(db, asset_id, current_user)
    db.commit()
    return {"status": "deleted", "asset_id": asset_id}

@router.post("/allocate_manual_override")
def manual_allocate(
    payload: AllocateRequest, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    """Emergency manual allocation (Bypasses Request workflow)."""
    trk=StockService.allocate_asset(
        db,
        payload.asset_id,
        payload.emp_id,
        payload.allocation_type,
        current_user,
        payload.movement_reason or "MANUAL_ALLOCATE",
    )
    db.commit()
    return trk

@router.post("/return_manual_override")
def manual_return(
    payload: ReturnRequest, 
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    """Emergency manual return (Bypasses Request workflow)."""
    trk=StockService.return_asset(db, payload.tracking_id, current_user, payload.movement_reason or "MANUAL_RETURN")
    db.commit()
    return {"status": "success", "recovered_asset": trk.asset_id}
# ============================================================================
# INSTANCE STATUS MANAGEMENT
# ============================================================================

@router.post("/instances/{instance_id}/repair")
def mark_instance_repair(
    instance_id: str,
    reason: Optional[str] = None,
    repair_cost: float = 0.0,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    """Mark an instance as IN_REPAIR."""
    instance = StockService.mark_in_repair(
        db, instance_id, current_user,
        reason or "SENT_FOR_REPAIR",
        repair_cost=repair_cost,
    )
    db.commit()
    return {
        "instance_id": instance.instance_id,
        "asset_id": instance.asset_id,
        "status": instance.status.value,
        "message": f"Instance marked as IN_REPAIR"
    }

@router.post("/instances/{instance_id}/repaired")
def mark_instance_repaired(
    instance_id: str,
    reason: Optional[str] = None,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    """Mark an instance as AVAILABLE after repair."""
    instance = StockService.mark_repaired(
        db, instance_id, current_user,
        reason or "REPAIR_COMPLETED"
    )
    db.commit()
    return {
        "instance_id": instance.instance_id,
        "asset_id": instance.asset_id,
        "status": instance.status.value,
        "message": f"Instance restored to AVAILABLE"
    }

@router.post("/instances/{instance_id}/damaged")
def mark_instance_damaged(
    instance_id: str,
    reason: Optional[str] = None,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.SUPPORT_TEAM))
):
    """Mark an instance as DAMAGED/NOT_USABLE."""
    instance = StockService.mark_damaged(
        db, instance_id, current_user,
        reason or "MARKED_DAMAGED"
    )
    db.commit()
    return {
        "instance_id": instance.instance_id,
        "asset_id": instance.asset_id,
        "status": instance.status.value,
        "message": f"Instance marked as DAMAGED"
    }

@router.post("/instances/{instance_id}/retire")
def retire_instance(
    instance_id: str,
    reason: Optional[str] = None,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    """Mark an instance as RETIRED (end of life)."""
    instance = StockService.retire_instance(
        db, instance_id, current_user,
        reason or "RETIRED"
    )
    db.commit()
    return {
        "instance_id": instance.instance_id,
        "asset_id": instance.asset_id,
        "status": instance.status.value,
        "message": f"Instance marked as RETIRED"
    }

@router.post("/instances/{instance_id}/transfer")
def transfer_asset(
    instance_id: str,
    to_emp_id: str,
    reason: Optional[str] = None,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR))
):
    """
    Transfer an asset from current assignee to another employee.
    Requires both employees to exist and current asset to be ASSIGNED.
    """
    # Verify target employee exists
    target_emp = apply_tenant_filter(db.query(Employee), current_user, Employee).filter(Employee.employee_id == to_emp_id).first()
    if not target_emp:
        raise HTTPException(status_code=404, detail=f"Employee {to_emp_id} not found")
    
    # Get instance to find current assignee
    instance = apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance).filter(
        AssetInstance.instance_id == instance_id
    ).first()
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    if not instance.assigned_to_id:
        raise HTTPException(
            status_code=400,
            detail=f"Instance {instance_id} is not assigned to anyone. Cannot transfer."
        )
    from_emp_id = instance.assigned_to_id
    
    trk = StockService.transfer_asset(
        db, instance_id, from_emp_id, to_emp_id, current_user,
        reason or "TRANSFER"
    )
    db.commit()
    
    return {
        "tracking_id": trk.tracking_id,
        "instance_id": instance_id,
        "from_emp_id": from_emp_id,
        "to_emp_id": to_emp_id,
        "status": "transferred",
        "message": f"Asset transferred from {from_emp_id} to {to_emp_id}"
    }


@router.post("/instances/{instance_id}/transfer-branch")
def transfer_instance_branch(
    instance_id: str,
    target_branch_id: str,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN, EmployeeRole.MANAGER)),
):
    """Transfer an unassigned AVAILABLE instance from one branch to another."""
    trk = StockService.transfer_instance_branch(
        db,
        instance_id=instance_id,
        target_branch_id=target_branch_id,
        user=current_user,
        reason=reason or "BRANCH_TRANSFER",
    )
    db.commit()
    return {
        "tracking_id": trk.tracking_id,
        "instance_id": instance_id,
        "target_branch_id": target_branch_id,
        "status": "branch_transferred",
    }

# ============================================================================
# LIFECYCLE TRACKING ANALYTICS
# ============================================================================

@router.get("/instances/{instance_id}/lifecycle")
def get_instance_lifecycle(
    instance_id: str,
    page: int = 1,
    per_page: int = 50,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    """Get complete lifecycle history for an asset instance."""
    # Verify instance exists
    instance = apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance).filter(
        AssetInstance.instance_id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    return LifecycleService.get_instance_lifecycle(db, instance_id, page, per_page)

@router.get("/assets/{asset_id}/lifecycle")
def get_asset_lifecycle(
    asset_id: str,
    page: int = 1,
    per_page: int = 50,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    """Get aggregate lifecycle history for all instances of an asset."""
    # Verify asset exists
    asset = apply_tenant_filter(db.query(Asset), current_user, Asset).filter(
        Asset.asset_id == asset_id
    ).first()
    
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    return LifecycleService.get_asset_lifecycle(db, asset_id, page, per_page)

@router.get("/assets/{asset_id}/lifecycle-analytics")
def get_asset_lifecycle_analytics(
    asset_id: str,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    """Get lifecycle analytics for an asset (repair count, downtime, age, etc)."""
    # Verify asset exists
    asset = apply_tenant_filter(db.query(Asset), current_user, Asset).filter(
        Asset.asset_id == asset_id
    ).first()
    
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    return LifecycleService.get_lifecycle_analytics(db, asset_id)

# ============================================================================
# INVENTORY ANALYTICS
# ============================================================================

@router.get("/inventory/{asset_id}")
def get_asset_inventory(
    asset_id: str,
    branch_id: Optional[str] = None,
    db: Session=Depends(get_db),
    current_user: Employee=Depends(get_current_user)
):
    """Get detailed inventory snapshot for a specific asset."""
    asset = apply_tenant_filter(db.query(Asset), current_user, Asset).filter(
        Asset.asset_id == asset_id
    ).first()
    
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    # Calculate inventory
    if branch_id:
        inventory = StockService.get_inventory_for_branch(db, asset_id, branch_id)
    else:
        inventory = StockService.get_inventory(db, asset_id)
    
    return {
        "asset_id": asset_id,
        "asset_name": asset.name,
        "branch_id": branch_id,
        "inventory": InventorySnapshot.from_service(inventory),
        "counts": {
            "total": inventory.total,
            "available": inventory.available,
            "assigned": inventory.assigned,
            "in_repair": inventory.in_repair,
            "not_usable": inventory.not_usable,
            "retired": inventory.retired,
        },
        "allocatable_count": inventory.allocatable()
    }
@router.post("/check-expirations")
def trigger_expiration_check(
    db: Session=Depends(get_db),
    current_user: Employee=Depends(require_roles(EmployeeRole.SUPER_ADMIN, EmployeeRole.ORG_ADMIN))
):
    """
    Manually triggers the daily scan for Warranty and License expirations.
    In production, this could be pinged by a cron job at midnight.
    """
    result = CronService.check_and_notify_expirations(db, current_user)
    return result

@router.get("/categories")
def get_categories(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    rows = apply_tenant_filter(db.query(Category), current_user, Category, allow_cross_branch=True)
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        rows = rows.filter(or_(Category.organization_id == current_user.organization_id, Category.organization_id.is_(None)))
    rows = rows.order_by(Category.category_name.asc()).all()
    if not rows and current_user.role == EmployeeRole.ORG_ADMIN:
        rows = db.query(Category).order_by(Category.category_name.asc()).all()
    logger.info("Dropdown returning %s items for /stock/categories", len(rows))
    return [
        {
            "id": row.category_id,
            "name": row.category_name,
            "category_id": row.category_id,
            "category_name": row.category_name,
            "description": row.description,
        }
        for row in rows
    ]

@router.get("/sub-categories")
def get_sub_categories(
    category_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    query = apply_tenant_filter(db.query(SubCategory), current_user, SubCategory, allow_cross_branch=True)
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        query = query.filter(or_(SubCategory.organization_id == current_user.organization_id, SubCategory.organization_id.is_(None)))
    if category_id:
        query = query.filter(SubCategory.category_id == category_id)
    rows = query.order_by(SubCategory.sub_category_name.asc()).all()
    if not rows and current_user.role == EmployeeRole.ORG_ADMIN:
        fallback_query = db.query(SubCategory)
        if category_id:
            fallback_query = fallback_query.filter(SubCategory.category_id == category_id)
        rows = fallback_query.order_by(SubCategory.sub_category_name.asc()).all()
    logger.info("Dropdown returning %s items for /stock/sub-categories", len(rows))
    return [
        {
            "id": row.sub_category_id,
            "name": row.sub_category_name,
            "sub_category_id": row.sub_category_id,
            "sub_category_name": row.sub_category_name,
            "category_id": row.category_id,
            "description": row.description,
        }
        for row in rows
    ]


@router.get("/attributes/options")
def get_attribute_options(
    sub_category_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    query = apply_tenant_filter(db.query(AssetAttribute), current_user, AssetAttribute, allow_cross_branch=True)
    if current_user.role != EmployeeRole.SUPER_ADMIN:
        query = query.filter(or_(AssetAttribute.organization_id == current_user.organization_id, AssetAttribute.organization_id.is_(None)))
    if sub_category_id:
        query = query.filter(AssetAttribute.sub_category_id == sub_category_id)

    attributes = query.order_by(AssetAttribute.attribute_name.asc()).all()
    if not attributes and current_user.role == EmployeeRole.ORG_ADMIN:
        fallback_query = db.query(AssetAttribute)
        if sub_category_id:
            fallback_query = fallback_query.filter(AssetAttribute.sub_category_id == sub_category_id)
        attributes = fallback_query.order_by(AssetAttribute.attribute_name.asc()).all()
    logger.info("Dropdown returning %s items for /stock/attributes/options", len(attributes))
    return [
        {
            "attribute_id": item.attribute_id,
            "attribute_name": item.attribute_name,
            "data_type": item.data_type,
            "is_required": item.is_required,
            "sub_category_id": item.sub_category_id,
        }
        for item in attributes
    ]

@router.get("/statuses")
def get_asset_statuses():
    return [s.value for s in AssetStatus]


@router.get("/branches-list")

def get_branches_list(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user)
):
    query = apply_tenant_filter(db.query(Branch), current_user, Branch)
    if active_only:
        query = query.filter(Branch.status == BranchStatus.ACTIVE)
    rows = query.order_by(Branch.branch_name.asc()).all()
    logger.info("Dropdown returning %s items for /stock/branches-list", len(rows))
    return [
        {
            "id": row.branch_id,
            "name": row.branch_name,
            "branch_id": row.branch_id,
            "branch_name": row.branch_name,
            "organization_id": row.organization_id,
            "status": row.status.value if hasattr(row.status, "value") else str(row.status),
            "location": row.location,
        }
        for row in rows
    ]
