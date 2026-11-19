import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.config import get_settings
from app.foundation.email import EmailNotConfiguredError, send_html_email, send_html_email_best_effort
from app.foundation.email_templates import render_email
from app.foundation.security import (
    create_access_token,
    generate_email_verification_token,
    generate_otp_code,
    generate_password_reset_token,
    generate_refresh_token,
    hash_email_verification_token,
    hash_otp_code,
    hash_password,
    hash_password_reset_token,
    hash_refresh_token,
    verify_password,
)
from app.modules.audit import service as audit_service
from app.modules.auth.models import EmailVerificationToken, OtpCode, PasswordResetToken, Session
from app.modules.auth.schemas import RegisterRequest
from app.modules.organizations.models import Organization
from app.modules.rbac.service import get_roles_for_user
from app.modules.users import service as users_service
from app.modules.users.models import User

settings = get_settings()
logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5  # provisional policy, see docs/open-questions.md
LOCKOUT_WINDOW_MINUTES = 15

GENERIC_AUTH_ERROR = "Invalid email or password"


class AuthenticationError(Exception):
    pass


class AccountLockedError(Exception):
    pass


async def authenticate(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    email: str,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    """Return (access_token, refresh_token). Unknown email and wrong password
    fail with the same message to prevent enumeration. The email lookup is
    case-insensitive to match accounts stored with mixed-case addresses."""
    stmt = select(User).where(
        User.organization_id == organization_id, func.lower(User.email) == email.lower()
    )
    user = (await db.execute(stmt)).scalar_one_or_none()

    if user is None:
        # Verify against a dummy hash so timing does not reveal whether the
        # account exists.
        verify_password(password, "$argon2id$v=19$m=65536,t=3,p=4$" + "0" * 22 + "$" + "0" * 43)
        # The organization_id comes from the client and may be stale; skip the
        # audit row rather than fail the login on a foreign-key error.
        if await db.get(Organization, organization_id) is not None:
            await audit_service.record(
                db, organization_id=organization_id, actor_user_id=None,
                action="login.failed", entity_type="user", entity_id=email,
                reason="unknown_email", ip_address=ip_address, user_agent=user_agent,
            )
            await db.commit()
        raise AuthenticationError(GENERIC_AUTH_ERROR)

    if user.status != "ACTIVE":
        # Admin-frozen account: same 423 handling as a lockout, distinguished
        # only by the message.
        raise AccountLockedError("This account has been disabled. Contact the administrator.")

    if user.locked_until and user.locked_until > datetime.now(UTC):
        raise AccountLockedError("Account temporarily locked, try again later")

    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=LOCKOUT_WINDOW_MINUTES)
            user.failed_login_attempts = 0
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=user.id,
            action="login.failed", entity_type="user", entity_id=str(user.id),
            reason="wrong_password", ip_address=ip_address, user_agent=user_agent,
        )
        await db.commit()
        raise AuthenticationError(GENERIC_AUTH_ERROR)

    user.failed_login_attempts = 0
    user.locked_until = None

    roles = await get_roles_for_user(db, user_id=user.id, organization_id=organization_id)
    access_token = create_access_token(
        subject=str(user.id), organization_id=str(organization_id), roles=roles
    )
    refresh_token = generate_refresh_token()
    session = Session(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user.id,
        action="login.success", entity_type="user", entity_id=str(user.id),
        ip_address=ip_address, user_agent=user_agent,
    )
    await db.commit()
    return access_token, refresh_token


async def rotate_refresh_token(
    db: AsyncSession, *, organization_id: uuid.UUID, refresh_token: str
) -> tuple[str, str]:
    """Revoke the presented refresh token's session and issue a new one, so a
    stolen token that gets reused is detectable and cannot be replayed."""
    token_hash = hash_refresh_token(refresh_token)
    stmt = select(Session).where(Session.refresh_token_hash == token_hash)
    session = (await db.execute(stmt)).scalar_one_or_none()

    if session is None or session.revoked_at is not None:
        raise AuthenticationError("Invalid refresh token")
    if session.expires_at < datetime.now(UTC):
        raise AuthenticationError("Refresh token expired")

    user = await db.get(User, session.user_id)
    if user is None or user.organization_id != organization_id:
        raise AuthenticationError("Invalid refresh token")

    session.revoked_at = datetime.now(UTC)

    roles = await get_roles_for_user(db, user_id=user.id, organization_id=organization_id)
    new_access_token = create_access_token(
        subject=str(user.id), organization_id=str(organization_id), roles=roles
    )
    new_refresh_token = generate_refresh_token()
    new_session = Session(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(new_refresh_token),
        user_agent=session.user_agent,
        ip_address=session.ip_address,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(new_session)
    await db.commit()
    return new_access_token, new_refresh_token


async def revoke_session(db: AsyncSession, *, refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    await db.execute(
        update(Session)
        .where(Session.refresh_token_hash == token_hash, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


async def revoke_all_sessions(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.commit()


class RegistrationError(Exception):
    pass


PRIVATE_LIKE_KINDS = {"PRIVATE", "SOLE_PROPRIETOR"}
COMPANY_LIKE_KINDS = {"COMPANY", "CONDOMINIUM"}


async def register_with_referral(db: AsyncSession, *, organization_id: uuid.UUID, payload: RegisterRequest) -> User:
    """Invite-only self-registration. The referral code is validated before
    anything is created; user, role, customer, profile/company and promoter
    attribution are then written in a single transaction, so a customer can
    never exist without an attribution."""
    from app.modules.customers.models import Company, Customer, CustomerProfile
    from app.modules.friend_referrals import service as friend_referrals_service
    from app.modules.friend_referrals.models import (
        REFERRAL_SOURCE_FRIEND_LINK,
        REFERRAL_SOURCE_PROMOTER_LINK,
    )
    from app.modules.network.models import AgentProfile
    from app.modules.rbac.models import Role, UserRole
    from app.modules.referral import service as referral_service
    from app.modules.referral.models import CustomerAttribution

    if payload.kind in PRIVATE_LIKE_KINDS and not (payload.first_name and payload.last_name):
        raise RegistrationError("first_name and last_name are required for this customer kind")
    if payload.kind in COMPANY_LIKE_KINDS and not payload.company_name:
        raise RegistrationError("company_name is required for this customer kind")

    # A referral code is resolved in this order:
    #   1. PROMOTER code: the customer joins that promoter's tree.
    #   2. INVITE code (friend_referral_codes): the customer is attributed to
    #      the inviter's own promoter, since plain customers cannot have a
    #      downline (friend_referrals/service.py::promoter_code_for_referrer).
    # Either way the customer is also added to the referrer's informational
    # invite list, which never affects the commercial tree or payouts.
    friend_code = None
    promoter_code = await referral_service.get_active_promoter_code(
        db, organization_id=organization_id, code=payload.referral_code
    )
    if promoter_code is None:
        friend_code = await friend_referrals_service.get_active_code(
            db, organization_id=organization_id, code=payload.referral_code
        )
        if friend_code is None:
            raise RegistrationError("Invalid or expired referral code -- registration is invite-only")
        promoter_code = await friend_referrals_service.promoter_code_for_referrer(
            db, organization_id=organization_id, user_id=friend_code.user_id
        )
        if promoter_code is None:
            # No active promoter left in the inviter's chain: refuse rather than
            # create a customer with no owner.
            raise RegistrationError(
                "Questo link di invito non è utilizzabile al momento -- contatta l'assistenza."
            )

    existing = (
        await db.execute(
            select(User).where(
                User.organization_id == organization_id, func.lower(User.email) == payload.email.lower()
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise RegistrationError("An account with this email already exists")

    role = (
        await db.execute(
            select(Role).where(
                (Role.organization_id == organization_id) | (Role.organization_id.is_(None)),
                Role.code == "CUSTOMER",
            )
        )
    ).scalars().first()
    if role is None:
        raise RegistrationError("Customer role is not configured for this organization")

    user = User(
        organization_id=organization_id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        status="ACTIVE",
    )
    db.add(user)
    await db.flush()
    # accept_privacy is already guaranteed by RegisterRequest's validator.
    await users_service.mark_privacy_accepted(db, user=user)

    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))

    customer = Customer(
        organization_id=organization_id,
        user_id=user.id,
        kind=payload.kind,
        email=payload.email,
        phone=payload.phone,
    )
    db.add(customer)
    await db.flush()

    if payload.kind in PRIVATE_LIKE_KINDS:
        db.add(CustomerProfile(customer_id=customer.id, first_name=payload.first_name, last_name=payload.last_name))
    else:
        db.add(Company(customer_id=customer.id, company_name=payload.company_name))

    db.add(
        CustomerAttribution(
            organization_id=organization_id,
            customer_id=customer.id,
            promoter_code_id=promoter_code.id,
            referral_session_id=None,
            attributed_at=datetime.now(UTC),
        )
    )

    # Record the one-level invite list entry. For a promoter link the referrer
    # is the promoter's own user account, if any. Informational only, so failures
    # here must never fail a completed registration.
    referrer_user_id = friend_code.user_id if friend_code is not None else None
    if referrer_user_id is None:
        agent = await db.get(AgentProfile, promoter_code.agent_id)
        referrer_user_id = agent.user_id if agent is not None else None
    if referrer_user_id is not None:
        await friend_referrals_service.record_referral(
            db,
            organization_id=organization_id,
            referrer_user_id=referrer_user_id,
            referred_customer_id=customer.id,
            code_used=payload.referral_code,
            source=REFERRAL_SOURCE_FRIEND_LINK if friend_code is not None else REFERRAL_SOURCE_PROMOTER_LINK,
        )

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user.id,
        action="auth.self_registered", entity_type="customer", entity_id=str(customer.id),
        new_value={"email": payload.email, "referral_code": payload.referral_code},
    )
    await db.commit()
    await db.refresh(user)
    await send_verification_email(db, user=user)
    return user


EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES = 60 * 24


class EmailVerificationError(Exception):
    pass


async def send_verification_email(db: AsyncSession, *, user: User) -> None:
    """Send the verification link required for new registrations
    (docs/business-rules.md#account-gates). Best-effort: registration is already
    committed, so an SMTP failure must not surface as an error."""
    token = generate_email_verification_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_email_verification_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES),
        )
    )
    await db.commit()

    verify_link = f"{settings.public_app_base_url}/verify-email?token={token}"
    html = render_email(
        preheader="Conferma il tuo indirizzo email per attivare il tuo account SOSNET",
        heading="Benvenuto in SOSNET!",
        body_html=(
            "<p>Grazie per esserti registrato. Per attivare il tuo account e iniziare a usare la dashboard, "
            "conferma il tuo indirizzo email cliccando il pulsante qui sotto.</p>"
            f"<p>Il link è valido per {EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES // 60} ore.</p>"
        ),
        cta_label="Conferma la mia email",
        cta_url=verify_link,
    )
    try:
        send_html_email(
            to=user.email,
            subject="Conferma la tua email - SOSNET",
            html_body=html,
            text_body=f"Conferma il tuo indirizzo email entro {EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES // 60} ore: {verify_link}",
        )
    except EmailNotConfiguredError:
        logger.warning("Verification email for %s (SMTP not configured) -- link: %s", user.email, verify_link)


async def verify_email(db: AsyncSession, *, token: str) -> User:
    token_hash = hash_email_verification_token(token)
    stmt = select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
    row = (await db.execute(stmt)).scalar_one_or_none()

    if row is None or row.used_at is not None:
        raise EmailVerificationError("Invalid or already-used verification link")
    if row.expires_at < datetime.now(UTC):
        raise EmailVerificationError("This verification link has expired")

    user = await db.get(User, row.user_id)
    if user is None:
        raise EmailVerificationError("Invalid or already-used verification link")

    user.email_verified_at = datetime.now(UTC)
    row.used_at = datetime.now(UTC)

    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id,
        action="auth.email_verified", entity_type="user", entity_id=str(user.id),
    )
    await db.commit()
    await db.refresh(user)
    return user


async def resend_verification_email(db: AsyncSession, *, user: User) -> None:
    if user.email_verified_at is not None:
        return
    await send_verification_email(db, user=user)


PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 60
# Invited customers may not open the email for days, hence a much longer
# expiry than a password reset.
ACCOUNT_INVITE_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7


class PasswordResetError(Exception):
    pass


async def send_account_invite_email(db: AsyncSession, *, user: User, invited_by_display_name: str) -> None:
    """First-access email for a customer created by a promoter
    (network/service.py::create_recruited_customer). The account has a random,
    never-revealed password, so this reuses the password-reset token and page
    with a longer expiry. Completing it also marks the email as verified."""
    settings = get_settings()
    token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=ACCOUNT_INVITE_TOKEN_EXPIRE_MINUTES),
        )
    )
    await db.commit()

    set_password_link = f"{settings.public_app_base_url}/reset-password?token={token}"
    html = render_email(
        preheader="Il tuo account SOSNET è pronto",
        heading="Il tuo account SOSNET è pronto",
        body_html=(
            f"<p>{invited_by_display_name} ha creato per te un account su SOSNET e attivato "
            "quanto concordato -- trovi già tutto configurato non appena accedi.</p>"
            "<p>Per accedere per la prima volta, scegli subito la tua password personale.</p>"
        ),
        cta_label="Imposta la tua password",
        cta_url=set_password_link,
    )
    send_html_email_best_effort(
        context=f"Account-invite email (user={user.id})",
        to=user.email,
        subject="Il tuo account SOSNET è pronto",
        html_body=html,
        text_body=(
            f"{invited_by_display_name} ha creato per te un account su SOSNET.\n\n"
            f"Imposta la tua password qui: {set_password_link}"
        ),
    )


async def request_password_reset(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    email: str,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Returns normally whether or not the email has an account, so the endpoint
    cannot be used for enumeration. The link is only ever sent to the account's
    own address."""
    stmt = select(User).where(
        User.organization_id == organization_id, func.lower(User.email) == email.lower()
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        await audit_service.record(
            db, organization_id=organization_id, actor_user_id=None,
            action="password_reset.requested", entity_type="user", entity_id=email,
            reason="unknown_email", ip_address=ip_address, user_agent=user_agent,
        )
        await db.commit()
        return

    token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
    )

    # Use the stored address: the lookup is case-insensitive.
    recipient = user.email
    reset_link = f"{settings.public_app_base_url}/reset-password?token={token}"
    intro_html = "<p>Hai richiesto di reimpostare la password del tuo account SOSNET.</p>"
    intro_text = "Hai richiesto di reimpostare la password del tuo account SOSNET.\n\n"
    subject = "Reimposta la tua password - SOSNET"

    html = render_email(
        preheader="Reimposta la tua password SOSNET",
        heading="Reimposta la tua password",
        body_html=(
            intro_html
            + f"<p>Il link scade tra {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minuti. Se non hai richiesto tu "
            "questa operazione, ignora questa email: la password resterà invariata.</p>"
        ),
        cta_label="Scegli una nuova password",
        cta_url=reset_link,
    )
    try:
        send_html_email(
            to=recipient,
            subject=subject,
            html_body=html,
            text_body=(
                intro_text
                + f"Apri questo link entro {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minuti per scegliere una nuova password:\n"
                f"{reset_link}\n\n"
                "Se non hai richiesto tu questa operazione, ignora questa email."
            ),
        )
        delivery = "sent"
    except EmailNotConfiguredError:
        # Without SMTP the link goes only to the process log (shell access
        # required), never to anything a web UI role can read, since that would let
        # an admin take over any account. See docs/business-rules.md.
        logger.warning("Password reset for %s (SMTP not configured) -- link: %s", recipient, reset_link)
        delivery = "logged_only"

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=user.id,
        action="password_reset.requested", entity_type="user", entity_id=str(user.id),
        # Never record the token itself.
        new_value={"delivery": delivery},
        ip_address=ip_address, user_agent=user_agent,
    )
    await db.commit()


async def reset_password(db: AsyncSession, *, token: str, new_password: str) -> None:
    token_hash = hash_password_reset_token(token)
    stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    reset_token = (await db.execute(stmt)).scalar_one_or_none()

    if reset_token is None or reset_token.used_at is not None:
        raise PasswordResetError("Invalid or already-used reset link")
    if reset_token.expires_at < datetime.now(UTC):
        raise PasswordResetError("This reset link has expired")

    user = await db.get(User, reset_token.user_id)
    if user is None:
        raise PasswordResetError("Invalid or already-used reset link")

    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    reset_token.used_at = datetime.now(UTC)
    # Completing an emailed link proves inbox control just like the
    # verify-email link, so an invited customer does not need a second email to
    # pass the account gates.
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)

    # A reset may mean the old password leaked: revoke every open session.
    await db.execute(
        update(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )

    await audit_service.record(
        db, organization_id=user.organization_id, actor_user_id=user.id,
        action="password_reset.completed", entity_type="user", entity_id=str(user.id),
    )
    await db.commit()


OTP_EXPIRE_MINUTES = 10

# Purpose constants are shared, never retyped, so a typo cannot split one
# gate into two. Used by network/service.py::apply_as_promoter.
PROMOTER_APPLICATION_OTP_PURPOSE = "PROMOTER_APPLICATION"
# Required when a self-checkout order spends wallet credit
# (credit_applied_cents > 0 on POST /orders/mine): a stolen session alone must
# not be enough to drain a wallet.
WALLET_CREDIT_SPEND_OTP_PURPOSE = "WALLET_CREDIT_SPEND"


async def request_otp(db: AsyncSession, *, user: User, purpose: str, context_line: str) -> None:
    """Email a one-time numeric code confirming a sensitive self-service action.
    Delivery is best-effort, with the same SMTP-missing fallback as other emails
    here."""
    code = generate_otp_code()
    db.add(
        OtpCode(
            user_id=user.id,
            purpose=purpose,
            code_hash=hash_otp_code(code),
            expires_at=datetime.now(UTC) + timedelta(minutes=OTP_EXPIRE_MINUTES),
        )
    )
    await db.commit()

    html = render_email(
        preheader="Il tuo codice di conferma SOSNET",
        heading="Codice di conferma",
        body_html=(
            f"<p>{context_line}</p>"
            f'<p style="font-size:28px; font-weight:700; letter-spacing:6px; color:#0a54e0; margin:20px 0;">{code}</p>'
            f"<p>Il codice scade tra {OTP_EXPIRE_MINUTES} minuti. Se non hai richiesto tu questo codice, ignora questa email.</p>"
        ),
    )
    try:
        send_html_email(
            to=user.email,
            subject="Il tuo codice di conferma - SOSNET",
            html_body=html,
            text_body=f"Il tuo codice di conferma: {code} (valido {OTP_EXPIRE_MINUTES} minuti)",
        )
    except EmailNotConfiguredError:
        logger.warning("OTP for %s purpose=%s not sent (SMTP not configured) -- code: %s", user.email, purpose, code)


async def verify_otp(db: AsyncSession, *, user_id: uuid.UUID, purpose: str, code: str) -> bool:
    """Consume the newest unused, unexpired code for this user/purpose. used_at
    is committed immediately so the code can never be replayed, whatever the
    outcome of the caller's action."""
    stmt = (
        select(OtpCode)
        .where(OtpCode.user_id == user_id, OtpCode.purpose == purpose, OtpCode.used_at.is_(None))
        .order_by(OtpCode.created_at.desc())
    )
    row = (await db.execute(stmt)).scalars().first()
    if row is None or row.expires_at < datetime.now(UTC) or row.code_hash != hash_otp_code(code):
        return False
    row.used_at = datetime.now(UTC)
    await db.commit()
    return True
