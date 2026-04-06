"""Company email and temporary password generation for employee onboarding."""

import re
import secrets
import string

from sqlalchemy.orm import Session

from app.server.schema.employee import Employee

COMPANY_DOMAIN = "kovan.com"


def generate_company_email(name: str, db: Session) -> str:
    raw = re.sub(r"[^a-z\s\-]", "", (name or "").lower())
    parts = [p for p in raw.replace("-", " ").split() if p]
    if len(parts) >= 2:
        base = f"{parts[0]}.{parts[1]}"
    elif len(parts) == 1:
        base = parts[0]
    else:
        base = "user"
    base = re.sub(r"[^a-z.]", "", base)
    if not base:
        base = "user"
    n = 0
    while True:
        suffix = f"{n}" if n else ""
        candidate = f"{base}{suffix}@{COMPANY_DOMAIN}"
        exists = db.query(Employee).filter(Employee.email == candidate).first()
        if not exists:
            return candidate
        n += 1
        if n > 5000:
            candidate = f"{base}.{secrets.token_hex(3)}@{COMPANY_DOMAIN}"
            if not db.query(Employee).filter(Employee.email == candidate).first():
                return candidate


def generate_temp_password() -> str:
    """Meets typical policy: 8+ chars, uppercase, digit, special."""
    upper = secrets.choice(string.ascii_uppercase)
    lower = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice("!@#$%")
    body = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
    return f"Temp@{upper}{lower}{digit}{special}{body[:2]}"
