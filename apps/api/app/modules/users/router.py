import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, require_permission
from app.modules.users import service as users_service
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/users", tags=["users"])

# Freeze and delete share a narrow permission held by SUPER_ADMIN only. Freeze
# is reversible and delete is not (users/service.py::delete_user), but both are
# sensitive account-lifecycle actions, kept outside the ADMIN tier that
# manages day-to-day records.


@router.patch("/{user_id}/freeze", response_model=UserRead)
async def freeze_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("users.manage_lifecycle")),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    try:
        user = await users_service.freeze_user(
            db, organization_id=current_user.organization_id, user_id=user_id, actor_user_id=current_user.user_id
        )
    except users_service.UserLifecycleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return UserRead.model_validate(user)


@router.patch("/{user_id}/unfreeze", response_model=UserRead)
async def unfreeze_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("users.manage_lifecycle")),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    user = await users_service.unfreeze_user(
        db, organization_id=current_user.organization_id, user_id=user_id, actor_user_id=current_user.user_id
    )
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return UserRead.model_validate(user)
