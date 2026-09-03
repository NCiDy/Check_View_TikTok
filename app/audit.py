from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditLog, User


def client_ip(request: Request) -> str | None:
    """Return the first proxy IP when Render forwards it, otherwise the peer IP."""
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded[:100]
    return request.client.host[:100] if request.client else None


def write_audit(
    db: Session,
    request: Request,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append a compact audit entry in the caller's existing transaction."""
    db.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            action=action[:100],
            entity_type=entity_type[:50],
            entity_id=str(entity_id)[:100] if entity_id is not None else None,
            details=details or {},
            ip_address=client_ip(request),
        )
    )
