import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user
from app.foundation.rate_limit import rate_limit
from app.modules.auth import service as auth_service
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MeRead,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.modules.users import service as users_service
from app.modules.users.models import User
from app.modules.users.schemas import ProfileRead, ProfileUpdate

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "sosnet_refresh_token"


@router.get("/me", response_model=MeRead)
async def get_me(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> MeRead:
    """Roles and account-gate flags read live from the DB, not from the access
    token. Roles can change mid-session (promoter activation, admin
    deactivation), and the dashboard's area switcher and blocking popups must
    react immediately rather than after the next token refresh."""
    from app.modules.rbac.service import get_roles_for_user

    roles = await get_roles_for_user(db, user_id=current_user.user_id, organization_id=current_user.organization_id)
    user = await db.get(User, current_user.user_id)
    return MeRead(
        roles=roles,
        email_verified=user is not None and user.email_verified_at is not None,
        profile_complete=user is not None and users_service.is_profile_complete(user),
        privacy_accepted=user is not None and user.privacy_accepted_at is not None,
    )


@router.get("/me/profile", response_model=ProfileRead)
async def get_my_profile(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ProfileRead:
    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return ProfileRead(
        fiscal_code=user.fiscal_code,
        residence_street=user.residence_street,
        residence_city=user.residence_city,
        residence_province=user.residence_province,
        residence_postal_code=user.residence_postal_code,
        residence_country=user.residence_country,
        is_complete=users_service.is_profile_complete(user),
    )


@router.patch("/me/profile", response_model=ProfileRead)
async def update_my_profile(
    payload: ProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileRead:
    """Backs the mandatory profile-completion popup; see
    docs/business-rules.md#profile-completion."""
    try:
        user = await users_service.update_profile(db, user_id=current_user.user_id, payload=payload)
    except users_service.ProfileUpdateError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ProfileRead(
        fiscal_code=user.fiscal_code,
        residence_street=user.residence_street,
        residence_city=user.residence_city,
        residence_province=user.residence_province,
        residence_postal_code=user.residence_postal_code,
        residence_country=user.residence_country,
        is_complete=users_service.is_profile_complete(user),
    )


@router.post(
    "/verify-email",
    dependencies=[Depends(rate_limit("verify-email", max_requests=10, window_seconds=300))],
)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await auth_service.verify_email(db, token=payload.token)
    except auth_service.EmailVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ok": True}


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("resend-verification", max_requests=3, window_seconds=300))],
)
async def resend_verification(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    user = await db.get(User, current_user.user_id)
    if user is not None:
        await auth_service.resend_verification_email(db, user=user)
    return {"ok": True}


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/api/auth",
    )


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit("login", max_requests=10, window_seconds=60))])
async def login(
    payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    organization_id = uuid.UUID(payload.organization_id)

    async def attempt() -> tuple[str, str]:
        return await auth_service.authenticate(
            db,
            organization_id=organization_id,
            email=payload.email,
            password=payload.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    try:
        try:
            access_token, refresh_token = await attempt()
        except auth_service.AuthenticationError:
            # SOS affiliates sign in with their Mamify account: if Mamify
            # accepts the credentials, the local login is created or aligned
            # and the normal path runs again.
            from app.modules.mamify import service as mamify_service

            if not await mamify_service.login_via_mamify(
                db, organization_id=organization_id, email=payload.email, password=payload.password
            ):
                raise
            access_token, refresh_token = await attempt()
    except auth_service.AccountLockedError as exc:
        raise HTTPException(status.HTTP_423_LOCKED, str(exc)) from exc
    except auth_service.AuthenticationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", max_requests=5, window_seconds=60))],
)
async def register(
    payload: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Public self-registration, invite-only: a valid referral_code is required.
    Does not log the user in; the client redirects to /login."""
    try:
        await auth_service.register_with_referral(
            db, organization_id=uuid.UUID(payload.organization_id), payload=payload
        )
    except auth_service.RegistrationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ok": True}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    organization_id: str,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing refresh token")
    try:
        access_token, new_refresh_token = await auth_service.rotate_refresh_token(
            db, organization_id=uuid.UUID(organization_id), refresh_token=refresh_token
        )
    except auth_service.AuthenticationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    _set_refresh_cookie(response, new_refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        await auth_service.revoke_session(db, refresh_token=refresh_token)
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/auth")


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("forgot-password", max_requests=5, window_seconds=300))],
)
async def forgot_password(
    payload: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    """Always 202, whether or not the email exists, to prevent account
    enumeration."""
    await auth_service.request_password_reset(
        db,
        organization_id=uuid.UUID(payload.organization_id),
        email=payload.email,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"ok": True}


@router.post(
    "/reset-password",
    dependencies=[Depends(rate_limit("reset-password", max_requests=10, window_seconds=300))],
)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await auth_service.reset_password(db, token=payload.token, new_password=payload.new_password)
    except auth_service.PasswordResetError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ok": True}
