"""CMDB configuration items and relationships."""

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.server.exceptions.base import ResourceNotFoundError
from app.server.schema.cmdb import CIRelationship, ConfigurationItem
from app.server.schema.employee import Employee, EmployeeRole


class CMDBService:
    VALID_CI_TYPES = {"ASSET", "SOFTWARE", "SERVICE", "USER", "NETWORK_DEVICE", "FURNITURE", "CLOUD", "OTHER"}
    VALID_REL_TYPES = {"depends_on", "connected_to", "assigned_to", "hosted_on"}

    @staticmethod
    def list_items(db: Session, current_user: Employee, ci_type: Optional[str] = None) -> List[ConfigurationItem]:
        if current_user.role not in (EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        q = db.query(ConfigurationItem)
        if ci_type:
            q = q.filter(ConfigurationItem.ci_type == ci_type.strip().upper())
        return q.order_by(ConfigurationItem.name.asc()).limit(500).all()

    @staticmethod
    def get_item(db: Session, ci_id: str, current_user: Employee) -> ConfigurationItem:
        if current_user.role not in (EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        row = db.query(ConfigurationItem).filter(ConfigurationItem.ci_id == ci_id).first()
        if not row:
            raise ResourceNotFoundError("ConfigurationItem", ci_id)
        return row

    @staticmethod
    def create_item(
        db: Session,
        current_user: Employee,
        *,
        ci_type: str,
        name: str,
        asset_id: Optional[str] = None,
        status: str = "ACTIVE",
    ) -> ConfigurationItem:
        if current_user.role not in (EmployeeRole.ADMIN, EmployeeRole.MANAGER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        t = ci_type.strip().upper()
        if t not in CMDBService.VALID_CI_TYPES:
            t = "OTHER"
        row = ConfigurationItem(ci_type=t, name=name.strip(), asset_id=asset_id, status=status.strip().upper())
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def list_relationships(db: Session, current_user: Employee, ci_id: Optional[str] = None) -> List[CIRelationship]:
        if current_user.role not in (EmployeeRole.ADMIN, EmployeeRole.MANAGER, EmployeeRole.HR, EmployeeRole.SUPPORT_TEAM):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        q = db.query(CIRelationship)
        if ci_id:
            q = q.filter((CIRelationship.source_ci == ci_id) | (CIRelationship.target_ci == ci_id))
        return q.limit(1000).all()

    @staticmethod
    def create_relationship(
        db: Session,
        current_user: Employee,
        *,
        source_ci: str,
        target_ci: str,
        relationship_type: str,
    ) -> CIRelationship:
        if current_user.role not in (EmployeeRole.ADMIN, EmployeeRole.MANAGER):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        rt = relationship_type.strip().lower()
        if rt not in CMDBService.VALID_REL_TYPES:
            raise ValueError(f"relationship_type must be one of {sorted(CMDBService.VALID_REL_TYPES)}")
        row = CIRelationship(source_ci=source_ci, target_ci=target_ci, relationship_type=rt)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
