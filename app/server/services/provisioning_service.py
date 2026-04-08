"""Company email and temporary password generation for employee onboarding."""

import os
import re
import secrets
import string

from sqlalchemy.orm import Session

from app.server.schema.employee import Employee

# Auto-generated company addresses when HR does not supply work email.
DEFAULT_COMPANY_DOMAIN = (os.getenv("DEFAULT_COMPANY_EMAIL_DOMAIN", "example.com") or "example.com").strip().lower()


def _normalize_domain(domain: str | None) -> str:
    raw = (domain or "").strip().lower()
    if not raw:
        return DEFAULT_COMPANY_DOMAIN
    # Only keep host portion if a scheme or path was provided.
    return raw.split("//")[-1].split("/")[0].split(":")[0].lstrip("www.") or DEFAULT_COMPANY_DOMAIN


def generate_company_email(name: str, db: Session, domain: str | None = None) -> str:
    company_domain = _normalize_domain(domain)
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
        candidate = f"{base}{suffix}@{company_domain}"
        exists = db.query(Employee).filter(Employee.email == candidate).first()
        if not exists:
            return candidate
        n += 1
        if n > 5000:
            candidate = f"{base}.{secrets.token_hex(3)}@{company_domain}"
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
