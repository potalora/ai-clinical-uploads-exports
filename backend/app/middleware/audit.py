from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


async def log_audit_event(
    db: AsyncSession,
    user_id: Optional[UUID],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[UUID] = None,
    ip_address: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Log an audit event to the audit_log table."""
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            details=details,
        )
        db.add(entry)
        await db.commit()
    except Exception:
        logger.exception("Failed to write audit log entry")
        await db.rollback()
