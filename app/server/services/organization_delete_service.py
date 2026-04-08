"""
Hard-delete an organization and all tenant-scoped rows (PostgreSQL FK-safe order).
"""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.server.schema.asset import Asset
from app.server.schema.attribute import AssetAttribute, AssetAttributeValue
from app.server.schema.audit import AuditLog
from app.server.schema.category import Category, SubCategory
from app.server.schema.cmdb import CIRelationship, ConfigurationItem
from app.server.schema.employee import Employee, EmployeePermission
from app.server.schema.organization import Branch, Organization
from app.server.schema.request import Request
from app.server.schema.tracking import Tracking


def purge_organization(db: Session, org: Organization) -> None:
    """Remove all data owned by this organization, then the caller may delete ``org``."""
    org_id = org.organization_id

    branch_ids = [b for (b,) in db.query(Branch.branch_id).filter(Branch.organization_id == org_id).all()]

    def or_filter(conditions: list):
        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return or_(*conditions)

    emp_parts = [Employee.organization_id == org_id]
    if branch_ids:
        emp_parts.append(Employee.branch_id.in_(branch_ids))
    emp_filter = or_filter(emp_parts)
    emp_ids = [r[0] for r in db.query(Employee.employee_id).filter(emp_filter).all()]

    asset_parts = [Asset.organization_id == org_id]
    if branch_ids:
        asset_parts.append(Asset.branch_id.in_(branch_ids))
    asset_filter = or_filter(asset_parts)
    asset_ids = [r[0] for r in db.query(Asset.asset_id).filter(asset_filter).all()]

    # 1) Audit logs for this tenant
    aud_parts = [AuditLog.organization_id == org_id]
    if branch_ids:
        aud_parts.append(AuditLog.branch_id.in_(branch_ids))
    db.query(AuditLog).filter(or_filter(aud_parts)).delete(synchronize_session=False)

    # 2) Tracking
    tr_parts = [Tracking.organization_id == org_id]
    if branch_ids:
        tr_parts.append(Tracking.branch_id.in_(branch_ids))
    if emp_ids:
        tr_parts.append(Tracking.emp_id.in_(emp_ids))
    if asset_ids:
        tr_parts.append(Tracking.asset_id.in_(asset_ids))
    db.query(Tracking).filter(or_filter(tr_parts)).delete(synchronize_session=False)

    # 3) Requests
    rq_parts = [Request.organization_id == org_id]
    if branch_ids:
        rq_parts.append(Request.branch_id.in_(branch_ids))
    if emp_ids:
        rq_parts.append(Request.emp_id.in_(emp_ids))
    db.query(Request).filter(or_filter(rq_parts)).delete(synchronize_session=False)

    # 4) Attribute values (asset-linked)
    v_parts = [AssetAttributeValue.organization_id == org_id]
    if branch_ids:
        v_parts.append(AssetAttributeValue.branch_id.in_(branch_ids))
    if asset_ids:
        v_parts.append(AssetAttributeValue.asset_id.in_(asset_ids))
    db.query(AssetAttributeValue).filter(or_filter(v_parts)).delete(synchronize_session=False)

    # 5) CMDB: relationships, then CIs
    ci_parts = [ConfigurationItem.organization_id == org_id]
    if branch_ids:
        ci_parts.append(ConfigurationItem.branch_id.in_(branch_ids))
    if asset_ids:
        ci_parts.append(ConfigurationItem.asset_id.in_(asset_ids))
    ci_filter = or_filter(ci_parts)
    ci_ids = [r[0] for r in db.query(ConfigurationItem.ci_id).filter(ci_filter).all()]
    rel_parts = [CIRelationship.organization_id == org_id]
    if branch_ids:
        rel_parts.append(CIRelationship.branch_id.in_(branch_ids))
    if ci_ids:
        rel_parts.append(CIRelationship.source_ci.in_(ci_ids))
        rel_parts.append(CIRelationship.target_ci.in_(ci_ids))
    db.query(CIRelationship).filter(or_filter(rel_parts)).delete(synchronize_session=False)
    db.query(ConfigurationItem).filter(ci_filter).delete(synchronize_session=False)

    # 6) Assets
    db.query(Asset).filter(asset_filter).delete(synchronize_session=False)

    # 7) Attribute definitions
    attr_parts = [AssetAttribute.organization_id == org_id]
    if branch_ids:
        attr_parts.append(AssetAttribute.branch_id.in_(branch_ids))
    db.query(AssetAttribute).filter(or_filter(attr_parts)).delete(synchronize_session=False)

    # 8) Categories / subcategories (tenant-owned rows only)
    sub_parts = [SubCategory.organization_id == org_id]
    if branch_ids:
        sub_parts.append(SubCategory.branch_id.in_(branch_ids))
    db.query(SubCategory).filter(or_filter(sub_parts)).delete(synchronize_session=False)

    cat_parts = [Category.organization_id == org_id]
    if branch_ids:
        cat_parts.append(Category.branch_id.in_(branch_ids))
    db.query(Category).filter(or_filter(cat_parts)).delete(synchronize_session=False)

    # 9) Employees & permissions
    perm_parts = [EmployeePermission.organization_id == org_id]
    if emp_ids:
        perm_parts.append(EmployeePermission.employee_id.in_(emp_ids))
    if branch_ids:
        perm_parts.append(EmployeePermission.branch_id.in_(branch_ids))
    db.query(EmployeePermission).filter(or_filter(perm_parts)).delete(synchronize_session=False)

    db.query(Employee).filter(emp_filter).delete(synchronize_session=False)

    # 10) Branches
    db.query(Branch).filter(Branch.organization_id == org_id).delete(synchronize_session=False)
