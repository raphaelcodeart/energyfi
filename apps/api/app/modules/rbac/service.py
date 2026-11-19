import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rbac.models import Permission, Role, RolePermission, UserRole


async def get_permission_codes_for_user(
    db: AsyncSession, *, user_id: uuid.UUID, organization_id: uuid.UUID
) -> set[str]:
    """All permission codes granted to a user within one organization.

    organization_id is mandatory: every caller must know which tenant it is
    authorizing for, so there is no cross-org variant.
    """
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            UserRole.organization_id == organization_id,
        )
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}


async def get_roles_for_user(
    db: AsyncSession, *, user_id: uuid.UUID, organization_id: uuid.UUID
) -> list[str]:
    stmt = (
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, UserRole.organization_id == organization_id)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def assign_role(
    db: AsyncSession, *, user_id: uuid.UUID, organization_id: uuid.UUID, role_code: str
) -> None:
    """Grant role_code on top of existing roles (a CUSTOMER approved as promoter
    keeps CUSTOMER). Idempotent thanks to the (user_id, organization_id,
    role_id) unique constraint. Does not commit."""
    role = (
        await db.execute(
            select(Role).where(
                (Role.organization_id == organization_id) | (Role.organization_id.is_(None)),
                Role.code == role_code,
            )
        )
    ).scalars().first()
    if role is None:
        raise ValueError(f"Role {role_code} is not configured for this organization")

    existing = (
        await db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.organization_id == organization_id,
                UserRole.role_id == role.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(UserRole(user_id=user_id, organization_id=organization_id, role_id=role.id))


async def revoke_role(
    db: AsyncSession, *, user_id: uuid.UUID, organization_id: uuid.UUID, role_code: str
) -> None:
    """Inverse of assign_role(), e.g. when a promoter is deactivated.
    Idempotent and does not commit."""
    role = (
        await db.execute(
            select(Role).where(
                (Role.organization_id == organization_id) | (Role.organization_id.is_(None)),
                Role.code == role_code,
            )
        )
    ).scalars().first()
    if role is None:
        return

    user_role = (
        await db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.organization_id == organization_id,
                UserRole.role_id == role.id,
            )
        )
    ).scalar_one_or_none()
    if user_role is not None:
        await db.delete(user_role)
