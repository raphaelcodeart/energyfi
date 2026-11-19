"""In-app notifications, fanned out to every user holding given roles (staff
events such as new contracts, tickets, approval requests) or sent to one user
(commission earned, approval outcome). See docs/business-rules.md#notifications."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification
from app.modules.rbac.models import Role, UserRole

# Roles notified of org-wide operational events. ACCOUNTING_OPERATOR and
# AUDITOR are excluded because they do not act on these events.
STAFF_NOTIFY_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN", "BACK_OFFICE_OPERATOR"}
# Only roles holding network.approve can act on a suggested promoter.
APPROVAL_NOTIFY_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN"}


def _add(db: AsyncSession, *, organization_id, recipient_user_id, type_, entity_type, entity_id, title, body=None):
    db.add(
        Notification(
            organization_id=organization_id, recipient_user_id=recipient_user_id, type=type_,
            entity_type=entity_type, entity_id=str(entity_id), title=title, body=body,
        )
    )


async def notify_user(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, type_: str,
    entity_type: str, entity_id, title: str, body: str | None = None,
) -> None:
    """Does not commit: the caller commits with the triggering event, as with
    audit_service.record()."""
    _add(db, organization_id=organization_id, recipient_user_id=user_id, type_=type_,
         entity_type=entity_type, entity_id=entity_id, title=title, body=body)


async def notify_roles(
    db: AsyncSession, *, organization_id: uuid.UUID, roles: set[str], type_: str,
    entity_type: str, entity_id, title: str, body: str | None = None, exclude_user_id: uuid.UUID | None = None,
) -> None:
    """One row per distinct user holding any of `roles`, so one admin marking
    it read does not clear it for the others."""
    stmt = (
        select(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.organization_id == organization_id, Role.code.in_(roles))
        .distinct()
    )
    user_ids = {row[0] for row in (await db.execute(stmt)).all()}
    if exclude_user_id is not None:
        user_ids.discard(exclude_user_id)
    for user_id in user_ids:
        _add(db, organization_id=organization_id, recipient_user_id=user_id, type_=type_,
             entity_type=entity_type, entity_id=entity_id, title=title, body=body)


async def list_my_notifications(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, unread_only: bool = False, limit: int = 50
) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.organization_id == organization_id, Notification.recipient_user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return list((await db.execute(stmt)).scalars().all())


async def mark_read(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification | None:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.organization_id != organization_id or notification.recipient_user_id != user_id:
        return None
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification


async def mark_all_read(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> int:
    result = await db.execute(
        update(Notification)
        .where(
            Notification.organization_id == organization_id,
            Notification.recipient_user_id == user_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.commit()
    return result.rowcount or 0
