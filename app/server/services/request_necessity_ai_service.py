"""Gemini-based recommendation: is a new asset request likely necessary given inventory and requester context."""

from __future__ import annotations

import json
import logging
import os
from enum import Enum
from typing import Any, Optional

import requests
from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.server.exceptions.base import ResourceNotFoundError
from app.server.schema.asset import Asset
from app.server.schema.category import Category
from app.server.schema.employee import Employee, EmployeeRole
from app.server.schema.request import Request
from app.server.schema.tracking import Tracking

logger = logging.getLogger(__name__)

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]


class NecessityVerdict(str, Enum):
    LIKELY_NEEDED = "LIKELY_NEEDED"
    UNCERTAIN = "UNCERTAIN"
    LIKELY_REDUNDANT = "LIKELY_REDUNDANT"


def _normalize_verdict(raw: str) -> NecessityVerdict:
    s = (raw or "").strip().upper().replace(" ", "_").replace("-", "_")
    if "REDUNDANT" in s or "NOT_NEEDED" in s or "UNNECESSARY" in s:
        return NecessityVerdict.LIKELY_REDUNDANT
    if "NEEDED" in s or "NECESSARY" in s or "JUSTIFIED" in s:
        if "NOT" in s or "UNLIKELY" in s:
            return NecessityVerdict.LIKELY_REDUNDANT
        return NecessityVerdict.LIKELY_NEEDED
    if "UNCERTAIN" in s or "UNKNOWN" in s or "REVIEW" in s:
        return NecessityVerdict.UNCERTAIN
    return NecessityVerdict.UNCERTAIN


def _analyze_reason_priority(reason: str) -> dict[str, Any]:
    text = (reason or "").strip().lower()
    if not text:
        return {
            "priority": "LOW",
            "signal": "missing_reason",
            "note": "Request reason is missing.",
        }

    high_signals = [
        "not working",
        "broken",
        "failed",
        "replace",
        "replacement",
        "repair",
        "onboarding",
        "new joiner",
        "cannot login",
        "production",
        "security",
        "urgent",
    ]
    medium_signals = [
        "slow",
        "performance",
        "upgrade",
        "project",
        "role change",
        "team expansion",
    ]

    if any(token in text for token in high_signals):
        return {
            "priority": "HIGH",
            "signal": "strong_business_reason",
            "note": "Reason includes failure/onboarding/critical work indicators.",
        }
    if any(token in text for token in medium_signals):
        return {
            "priority": "MEDIUM",
            "signal": "moderate_business_reason",
            "note": "Reason includes moderate operational justification.",
        }

    # Short, generic requests should be treated as weak justification.
    return {
        "priority": "LOW",
        "signal": "weak_or_generic_reason",
        "note": "Reason appears generic; justification quality is low.",
    }


def _call_gemini_json(prompt: str) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")

    last_detail = ""
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            resp = requests.post(
                url,
                params={"key": api_key},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=55,
            )
            if resp.status_code != 200:
                last_detail = f"{model}: HTTP {resp.status_code} {resp.text[:400]}"
                logger.warning("Gemini model failed: %s", last_detail)
                continue
            data = resp.json()
            cands = data.get("candidates") or []
            if not cands:
                last_detail = f"{model}: no candidates {data}"
                continue
            parts = (cands[0].get("content") or {}).get("parts") or []
            if not parts:
                last_detail = f"{model}: empty parts"
                continue
            text = (parts[0].get("text") or "").strip()
            if not text:
                last_detail = f"{model}: blank text"
                continue
            return json.loads(text)
        except json.JSONDecodeError as e:
            last_detail = f"{model}: invalid JSON {e}"
            logger.warning("Gemini JSON decode: %s", last_detail)
        except Exception as e:
            last_detail = f"{model}: {e}"
            logger.warning("Gemini error: %s", last_detail)
    raise RuntimeError(f"Gemini did not return usable JSON. Last detail: {last_detail}")


def _gather_context(db: Session, user: Employee, asset_category: str) -> dict[str, Any]:
    branch = (user.branch or "").strip() or None

    assigned: list[dict[str, Any]] = []
    rows = (
        db.query(Tracking)
        .options(joinedload(Tracking.asset).joinedload(Asset.category))
        .filter(Tracking.emp_id == user.employee_id, Tracking.returned_at == None)
        .all()
    )
    for tr in rows:
        a = tr.asset
        if not a:
            continue
        cat_name = a.category.category_name if a.category else None
        assigned.append(
            {
                "asset_id": a.asset_id,
                "name": a.name,
                "category": cat_name,
                "branch": a.branch,
            }
        )

    stock_branch: Optional[dict[str, Any]] = None
    if branch:
        cat_filter = (asset_category or "").strip()
        q = (
            db.query(
                func.count(Asset.asset_id).label("lines"),
                func.coalesce(func.sum(Asset.unused), 0).label("units_available"),
            )
            .join(Category, Asset.category_id == Category.category_id)
            .filter(Asset.branch == branch)
        )
        if cat_filter:
            q = q.filter(
                or_(
                    Category.category_name.ilike(cat_filter),
                    Category.category_name.ilike(f"%{cat_filter}%"),
                )
            )
        row = q.first()
        if row:
            stock_branch = {
                "branch": branch,
                "category_filter": cat_filter,
                "catalog_lines_in_category": int(row.lines or 0),
                "total_unused_units_in_category": int(row.units_available or 0),
            }

    recent: list[dict[str, Any]] = []
    for req in (
        db.query(Request)
        .filter(Request.emp_id == user.employee_id)
        .order_by(Request.req_date.desc())
        .limit(6)
        .all()
    ):
        recent.append(
            {
                "asset_name": req.asset_name,
                "asset_category": req.asset_category,
                "reason_snippet": (req.reason or "")[:120],
                "status": req.status,
                "stage": req.stage,
            }
        )

    return {
        "requester": {
            "employee_id": user.employee_id,
            "name": user.name,
            "role": user.role.value if user.role else None,
            "branch": user.branch,
        },
        "currently_assigned_active_assets": assigned,
        "branch_inventory_summary_for_requested_category": stock_branch,
        "recent_asset_requests_by_same_user": recent,
    }


def recommend_request_necessity(
    db: Session,
    requester: Employee,
    *,
    asset_name: str,
    asset_category: str,
    reason: str,
    ticket_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    asset_name = asset_name.strip()
    asset_category = asset_category.strip()
    reason = reason.strip()
    if not asset_name or not asset_category or not reason:
        raise ValueError("asset_name, asset_category, and reason are required.")

    context = _gather_context(db, requester, asset_category)
    context["reason_first_priority"] = _analyze_reason_priority(reason)
    if ticket_context:
        context["ticket_being_reviewed"] = ticket_context
    context_json = json.dumps(context, indent=2, default=str)

    ticket_note = ""
    if ticket_context:
        ticket_note = (
            "\nThis is an existing ticket already in the workflow; use ticket_being_reviewed for stage/status. "
            "The request lines below match that ticket.\n"
        )

    prompt = f"""You are an IT asset analyst helping HR and Admin judge whether an asset request is justified. You must NOT invent inventory numbers: only use the JSON context below.

Context (JSON):
{context_json}
{ticket_note}
Request (from the employee named in requester in the JSON):
- Requested asset name or description: {asset_name}
- Requested category: {asset_category}
- Stated reason: {reason}

Task: Judge whether this request is LIKELY_NEEDED, LIKELY_REDUNDANT, or UNCERTAIN.
Decision rule priority (strict):
1) FIRST PRIORITY: evaluate the quality and business necessity of the stated reason.
2) Then validate reason against assigned assets, branch stock, and recent request history.
3) If reason is weak/generic and overlaps existing assets, lean LIKELY_REDUNDANT.
4) If reason is strong (failure/onboarding/critical work) and no clear conflict exists, lean LIKELY_NEEDED.
- LIKELY_REDUNDANT: e.g. they already hold a suitable asset of the same class and the reason does not justify another (duplicate laptop without clear business case), or the reason is vague and overlaps existing assignments.
- LIKELY_NEEDED: e.g. clear failure/replacement need, onboarding, first device of that type, role change, or no conflicting assignment.
- UNCERTAIN: not enough information or mixed signals.

Respond with ONLY valid JSON (no markdown) in this exact shape:
{{
  "verdict": "LIKELY_NEEDED" | "UNCERTAIN" | "LIKELY_REDUNDANT",
  "confidence": <integer 0-100>,
  "summary": "<2-4 sentences, plain language>",
  "factors": ["<short bullet>", "..."]
}}
"""

    raw = _call_gemini_json(prompt)
    verdict = _normalize_verdict(str(raw.get("verdict", "")))
    try:
        conf = int(raw.get("confidence", 50))
    except (TypeError, ValueError):
        conf = 50
    conf = max(0, min(100, conf))
    summary = str(raw.get("summary", "")).strip() or "No summary returned."
    factors = raw.get("factors")
    if not isinstance(factors, list):
        factors = []
    factors = [str(x).strip() for x in factors if str(x).strip()][:8]

    return {
        "verdict": verdict.value,
        "confidence": conf,
        "summary": summary,
        "factors": factors,
        "model_note": "Advisory only; HR/Admin make final decisions.",
    }


def recommend_necessity_for_request(db: Session, viewer: Employee, request_id: str) -> dict[str, Any]:
    req = (
        db.query(Request)
        .options(joinedload(Request.employee))
        .filter(Request.request_id == request_id)
        .first()
    )
    if not req:
        raise ResourceNotFoundError("Request", request_id)

    requester = req.employee
    if not requester:
        raise ResourceNotFoundError("Employee", req.emp_id)

    # Permission model:
    # - HR: same-branch requests only.
    # - Org Admin: any request within their organization.
    # - Super Admin: any request.
    if viewer.role == EmployeeRole.HR:
        if (requester.branch or "").strip() != (viewer.branch or "").strip():
            raise HTTPException(
                status_code=403,
                detail="You can only run necessity review for requests from your branch.",
            )
    elif viewer.role == EmployeeRole.ORG_ADMIN:
        if req.organization_id and viewer.organization_id and req.organization_id != viewer.organization_id:
            raise HTTPException(
                status_code=403,
                detail="You can only run necessity review for requests in your organization.",
            )
    elif viewer.role != EmployeeRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only HR or Admin may request AI necessity analysis.")

    if (req.stage or "").strip() != "HR_VERIFICATION":
        raise HTTPException(
            status_code=400,
            detail="AI necessity recommendation is available only during HR_VERIFICATION stage.",
        )

    asset_name = (req.asset_name or "").strip()
    asset_category = (req.asset_category or "Unknown").strip()
    reason = (req.reason or "").strip() or "No reason text provided on the request."

    ticket_context = {
        "request_id": req.request_id,
        "stage": req.stage,
        "status": req.status,
        "request_type": req.request_type,
        "priority": req.priority,
        "severity": req.severity,
        "urgency": req.urgency,
        "hr_verified": req.hr_verified,
    }

    return recommend_request_necessity(
        db,
        requester,
        asset_name=asset_name,
        asset_category=asset_category,
        reason=reason,
        ticket_context=ticket_context,
    )
