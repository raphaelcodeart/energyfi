import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.config import get_settings
from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.foundation.rate_limit import rate_limit
from app.modules.organizations.features import require_feature
from app.modules.invoice_redemptions import service as redemptions_service
from app.modules.invoice_redemptions.schemas import (
    InvoiceRedemptionCheckoutSessionRead,
    InvoiceRedemptionPaymentMethodUpdate,
    InvoiceRedemptionPaymentProofUrlRead,
    InvoiceRedemptionRead,
    InvoiceRedemptionRejectRequest,
    InvoiceRedemptionUrlRead,
    InvoiceRedemptionVerifyRequest,
    PaymentInfoRead,
)
from app.modules.organizations import service as organizations_service
from app.modules.payments import service as payments_service

router = APIRouter(prefix="/invoice-redemptions", tags=["invoice-redemptions"])


def _redemption_error_to_http(exc: redemptions_service.InvoiceRedemptionError) -> HTTPException:
    if isinstance(exc, (redemptions_service.InvalidRedemptionStateError, redemptions_service.InvalidPaymentMethodError,
                         redemptions_service.PaymentMethodNotAvailableError, redemptions_service.PaymentProofError)):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get("/payment-info", response_model=PaymentInfoRead)
async def get_payment_info(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PaymentInfoRead:
    """Bank details for the redemption fee. The IBAN from organization settings
    takes precedence over COMPANY_BANK_IBAN in the environment; iban is None
    when neither is set."""
    org_settings = await organizations_service.get_settings(db, organization_id=current_user.organization_id)
    settings = get_settings()
    iban = org_settings["bank_iban"] or settings.company_bank_iban or None
    holder = org_settings["bank_account_holder"] or settings.company_bank_holder
    return PaymentInfoRead(iban=iban, holder=holder, instructions=org_settings["bank_transfer_instructions"])


@router.post(
    "",
    response_model=InvoiceRedemptionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_feature("invoice_cashback")), Depends(rate_limit("invoice-redemption-submit", max_requests=20, window_seconds=300))],
)
async def submit_invoice_redemption(
    partner_id: uuid.UUID = Form(...),
    declared_amount_cents: int = Form(...),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    """Open to any authenticated user, customer or promoter."""
    file_bytes = await file.read()
    try:
        redemption = await redemptions_service.submit_redemption(
            db,
            organization_id=current_user.organization_id,
            customer_user_id=current_user.user_id,
            partner_id=partner_id,
            declared_amount_cents=declared_amount_cents,
            file_bytes=file_bytes,
            content_type=file.content_type or "",
            original_filename=file.filename or "fattura",
        )
    except redemptions_service.PartnerNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except redemptions_service.RedemptionValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))


@router.get("/mine", response_model=list[InvoiceRedemptionRead])
async def list_my_invoice_redemptions(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceRedemptionRead]:
    rows = await redemptions_service.list_mine(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    return [InvoiceRedemptionRead(**d) for d in await redemptions_service.hydrate(db, rows)]


@router.get("/mine/{redemption_id}/photo-url", response_model=InvoiceRedemptionUrlRead)
async def get_my_invoice_redemption_photo_url(
    redemption_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionUrlRead:
    redemption = await redemptions_service.get_owned(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, redemption_id=redemption_id
    )
    if redemption is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice redemption not found")
    return InvoiceRedemptionUrlRead(url=redemptions_service.presigned_photo_url(redemption))


@router.patch("/mine/{redemption_id}/payment-method", response_model=InvoiceRedemptionRead)
async def change_my_redemption_payment_method(
    redemption_id: uuid.UUID,
    payload: InvoiceRedemptionPaymentMethodUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    """Switch a PAYMENT_PENDING redemption between card and bank transfer;
    owner only."""
    redemption = await redemptions_service.get_owned(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, redemption_id=redemption_id
    )
    if redemption is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice redemption not found")
    try:
        redemption = await redemptions_service.change_payment_method(
            db, organization_id=current_user.organization_id, redemption=redemption,
            new_payment_method=payload.payment_method,
        )
    except redemptions_service.InvoiceRedemptionError as exc:
        raise _redemption_error_to_http(exc) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))


@router.post("/mine/{redemption_id}/checkout-session", response_model=InvoiceRedemptionCheckoutSessionRead)
async def create_my_redemption_checkout_session(
    redemption_id: uuid.UUID,
    success_url: str,
    cancel_url: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionCheckoutSessionRead:
    """Owner only (404 for other users' redemptions). Charges only the
    CASHBACK_PERCENTAGE fee, never the invoice value."""
    redemption = await redemptions_service.get_owned(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, redemption_id=redemption_id
    )
    if redemption is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice redemption not found")
    if redemption.status != "PAYMENT_PENDING":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot pay a redemption in status {redemption.status}")
    try:
        checkout_url = await payments_service.create_checkout_session_for_redemption(
            db, organization_id=current_user.organization_id, redemption=redemption,
            success_url=success_url, cancel_url=cancel_url,
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return InvoiceRedemptionCheckoutSessionRead(checkout_url=checkout_url)


@router.post(
    "/mine/{redemption_id}/payment-proof",
    response_model=InvoiceRedemptionRead,
    dependencies=[Depends(rate_limit("payment-proof-upload", max_requests=20, window_seconds=300))],
)
async def upload_my_redemption_payment_proof(
    redemption_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    """Attach a bank-transfer receipt: evidence for the admin, not a payment
    confirmation."""
    redemption = await redemptions_service.get_owned(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, redemption_id=redemption_id
    )
    if redemption is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice redemption not found")
    file_bytes = await file.read()
    try:
        redemption = await redemptions_service.upload_payment_proof(
            db, organization_id=current_user.organization_id, redemption=redemption,
            file_bytes=file_bytes, content_type=file.content_type or "",
            original_filename=file.filename or "prova-pagamento", actor_user_id=current_user.user_id,
        )
    except redemptions_service.PaymentProofError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))


@router.get("/mine/{redemption_id}/payment-proof-url", response_model=InvoiceRedemptionPaymentProofUrlRead)
async def get_my_redemption_payment_proof_url(
    redemption_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionPaymentProofUrlRead:
    redemption = await redemptions_service.get_owned(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id, redemption_id=redemption_id
    )
    if redemption is None or redemption.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment proof not found")
    return InvoiceRedemptionPaymentProofUrlRead(url=redemptions_service.presigned_payment_proof_url(redemption))


@router.get("/admin", response_model=list[InvoiceRedemptionRead])
async def list_invoice_redemptions_admin(
    status_filter: str | None = None,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceRedemptionRead]:
    """Requires wallet.manage: this queue leads to minting wallet credit."""
    rows = await redemptions_service.list_admin_queue(
        db, organization_id=current_user.organization_id, status_filter=status_filter
    )
    return [InvoiceRedemptionRead(**d) for d in await redemptions_service.hydrate(db, rows)]


@router.get("/admin/{redemption_id}/photo-url", response_model=InvoiceRedemptionUrlRead)
async def get_invoice_redemption_photo_url_admin(
    redemption_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionUrlRead:
    redemption = await redemptions_service.get_org_scoped(
        db, organization_id=current_user.organization_id, redemption_id=redemption_id
    )
    if redemption is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice redemption not found")
    return InvoiceRedemptionUrlRead(url=redemptions_service.presigned_photo_url(redemption))


@router.get("/admin/{redemption_id}/payment-proof-url", response_model=InvoiceRedemptionPaymentProofUrlRead)
async def get_invoice_redemption_payment_proof_url_admin(
    redemption_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionPaymentProofUrlRead:
    redemption = await redemptions_service.get_org_scoped(
        db, organization_id=current_user.organization_id, redemption_id=redemption_id
    )
    if redemption is None or redemption.payment_proof_storage_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment proof not found")
    return InvoiceRedemptionPaymentProofUrlRead(url=redemptions_service.presigned_payment_proof_url(redemption))


@router.post("/admin/{redemption_id}/verify", response_model=InvoiceRedemptionRead)
async def verify_invoice_redemption(
    redemption_id: uuid.UUID,
    payload: InvoiceRedemptionVerifyRequest,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    try:
        redemption = await redemptions_service.verify(
            db,
            organization_id=current_user.organization_id,
            redemption_id=redemption_id,
            confirmed_amount_cents=payload.confirmed_amount_cents,
            actor_user_id=current_user.user_id,
        )
    except redemptions_service.InvalidRedemptionStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except redemptions_service.InvoiceRedemptionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))


@router.post("/admin/{redemption_id}/reject", response_model=InvoiceRedemptionRead)
async def reject_invoice_redemption(
    redemption_id: uuid.UUID,
    payload: InvoiceRedemptionRejectRequest,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    try:
        redemption = await redemptions_service.reject(
            db,
            organization_id=current_user.organization_id,
            redemption_id=redemption_id,
            reason=payload.reason,
            actor_user_id=current_user.user_id,
        )
    except redemptions_service.InvalidRedemptionStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except redemptions_service.InvoiceRedemptionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))


@router.post("/admin/{redemption_id}/confirm-payment", response_model=InvoiceRedemptionRead)
async def confirm_invoice_redemption_payment(
    redemption_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRedemptionRead:
    try:
        redemption = await redemptions_service.confirm_payment(
            db, organization_id=current_user.organization_id, redemption_id=redemption_id,
            actor_user_id=current_user.user_id,
        )
    except redemptions_service.InvalidRedemptionStateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except redemptions_service.InvoiceRedemptionError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return InvoiceRedemptionRead(**(await redemptions_service.to_read_dict(db, redemption)))
