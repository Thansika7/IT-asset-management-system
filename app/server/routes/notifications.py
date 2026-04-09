from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.server.auth.service import get_current_user
from app.server.database.database import get_db
from app.server.schema.employee import Employee
from app.server.services.notification_service import NotificationService


router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationReadItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notification_id: str
    scope: str
    event_type: str | None = None
    priority: str
    title: str
    message: str
    status: str
    retry_count: int
    last_attempt: str | None = None
    read: bool
    changed_at: str | None = None


class NotificationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: List[dict]
    total: int
    page: int
    per_page: int


class NotificationReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notification_ids: List[str] = Field(default_factory=list)


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    payload = NotificationService.list_notifications(db, current_user, unread_only=False, page=page, per_page=per_page)
    payload["items"] = [
        {
            **item,
            "changed_at": item.get("changed_at").isoformat() if item.get("changed_at") else None,
        }
        for item in payload["items"]
    ]
    return payload


@router.get("/unread", response_model=NotificationListResponse)
def list_unread_notifications(
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    payload = NotificationService.list_notifications(db, current_user, unread_only=True, page=page, per_page=per_page)
    payload["items"] = [
        {
            **item,
            "changed_at": item.get("changed_at").isoformat() if item.get("changed_at") else None,
        }
        for item in payload["items"]
    ]
    return payload


@router.post("/read")
def mark_notifications_read(
    body: NotificationReadRequest,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    result = NotificationService.mark_read(db, current_user, body.notification_ids)
    db.commit()
    return {"status": "success", **result}
