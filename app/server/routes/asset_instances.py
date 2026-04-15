from typing import Optional
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.server.auth.service import get_current_user
from app.server.database.database import get_db
from app.server.database.tenant import apply_tenant_filter
from app.server.models.stock import (
	AssetInstanceFilterOptionsResponse,
	AssetInstanceListItem,
	AssetInstancePagedResponse,
	FilterOption,
)
from app.server.schema.asset import Asset, AssetInstance, AssetStatus
from app.server.schema.category import Category
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.organization import Branch, BranchStatus


router = APIRouter(prefix="/asset-instances", tags=["asset_instances"])
logger = logging.getLogger(__name__)


@router.get("", response_model=AssetInstancePagedResponse)
def list_asset_instances(
	search: Optional[str] = None,
	status: Optional[str] = None,
	branch_id: Optional[str] = None,
	category_id: Optional[str] = None,
	assigned_to_id: Optional[str] = None,
	page: int = 1,
	per_page: int = 20,
	db: Session = Depends(get_db),
	current_user: Employee = Depends(get_current_user),
):
	query = (
		apply_tenant_filter(
			db.query(AssetInstance)
			.join(AssetInstance.model)
			.outerjoin(Asset.category)
			.outerjoin(AssetInstance.assigned_to)
			.outerjoin(AssetInstance.branch_rel),
			current_user,
			AssetInstance,
		)
	)

	if current_user.role in [EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE] and current_user.branch_id:
		query = query.filter(AssetInstance.branch_id == current_user.branch_id)

	if status:
		query = query.filter(AssetInstance.status == status.upper())
	if branch_id:
		query = query.filter(AssetInstance.branch_id == branch_id)
	if category_id:
		query = query.filter(Asset.category_id == category_id)
	if assigned_to_id:
		query = query.filter(AssetInstance.assigned_to_id == assigned_to_id)

	if search:
		needle = f"%{search.strip()}%"
		query = query.filter(
			or_(
				AssetInstance.instance_id.ilike(needle),
				AssetInstance.serial_number.ilike(needle),
				Asset.name.ilike(needle),
				Employee.name.ilike(needle),
				Employee.employee_id.ilike(needle),
			)
		)

	total = query.count()
	rows = query.order_by(AssetInstance.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

	items = [
		AssetInstanceListItem(
			instance_id=row.instance_id,
			asset_id=row.asset_id,
			asset_name=row.model.name if row.model else row.asset_id,
			brand=row.model.brand if row.model else None,
			model=row.model.model if row.model else None,
			serial_number=row.serial_number,
			branch_id=row.branch_id,
			branch=(row.branch_rel.branch_name if row.branch_rel else (row.model.branch if row.model else None)),
			status=row.status.value if hasattr(row.status, "value") else str(row.status),
			assigned_to_id=row.assigned_to_id,
			assigned_to=(row.assigned_to.name if row.assigned_to else row.assigned_to_id),
			category_id=(row.model.category_id if row.model else None),
			category=(row.model.category.category_name if row.model and row.model.category else None),
		)
		for row in rows
	]

	return {
		"items": items,
		"total": total,
		"page": page,
		"per_page": per_page,
	}


@router.get("/options", response_model=AssetInstanceFilterOptionsResponse)
def list_asset_instance_options(
	db: Session = Depends(get_db),
	current_user: Employee = Depends(get_current_user),
):
	scoped = apply_tenant_filter(db.query(AssetInstance), current_user, AssetInstance)
	if current_user.role in [EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM, EmployeeRole.EMPLOYEE] and current_user.branch_id:
		scoped = scoped.filter(AssetInstance.branch_id == current_user.branch_id)

	branch_ids = [
		row[0]
		for row in scoped.with_entities(AssetInstance.branch_id).distinct().all()
		if row[0]
	]
	assignee_ids = [
		row[0]
		for row in scoped.with_entities(AssetInstance.assigned_to_id).distinct().all()
		if row[0]
	]
	category_ids = [
		row[0]
		for row in scoped.join(AssetInstance.model).with_entities(Asset.category_id).distinct().all()
		if row[0]
	]

	branches = (
		apply_tenant_filter(db.query(Branch), current_user, Branch)
		.filter(Branch.branch_id.in_(branch_ids))
		.filter(Branch.status == BranchStatus.ACTIVE)
		.order_by(Branch.branch_name.asc())
		.all()
		if branch_ids
		else []
	)
	assignees = (
		apply_tenant_filter(db.query(Employee), current_user, Employee)
		.filter(Employee.employee_id.in_(assignee_ids))
		.order_by(Employee.name.asc())
		.all()
		if assignee_ids
		else []
	)
	categories = (
		apply_tenant_filter(db.query(Category), current_user, Category)
		.filter(Category.category_id.in_(category_ids))
		.order_by(Category.category_name.asc())
		.all()
		if category_ids
		else []
	)

	status_allow = {"NEW", "AVAILABLE", "ASSIGNED", "IN_REPAIR", "NOT_USABLE", "RETIRED"}
	statuses = [status.value for status in AssetStatus if status.value in status_allow]

	logger.info(
		"Dropdown returning statuses=%s branches=%s categories=%s assignees=%s for /asset-instances/options",
		len(statuses),
		len(branches),
		len(categories),
		len(assignees),
	)

	return {
		"statuses": statuses,
		"branches": [FilterOption(value=b.branch_id, label=b.branch_name) for b in branches],
		"categories": [FilterOption(value=c.category_id, label=c.category_name) for c in categories],
		"assignees": [FilterOption(value=e.employee_id, label=e.name) for e in assignees],
	}
