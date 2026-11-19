import urllib.parse
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.modules.audit import service as audit_service
from app.modules.catalog import pricing
from app.modules.catalog.models import ProductVersion
from app.modules.contracts import dossier, payment_plans
from app.modules.contracts import service as contract_service
from app.modules.contracts.models import Contract
from app.modules.contracts.schemas import (
    ContractCheckoutRequest,
    ContractCreate,
    ContractForCustomerCreate,
    ContractIbanUpdate,
    ContractPaymentOptionRead,
    ContractPaymentOptionsRead,
    ContractRead,
    ContractSelfServiceCreate,
    ContractStatusHistoryRead,
    ContractTransitionRequest,
)
from app.modules.contracts.service import InvalidProducerAgentError, SelfServiceContractError
from app.modules.contracts.state_machine import InvalidTransitionError
from app.modules.customers.models import Customer
from app.modules.integrations import google_drive
from app.modules.integrations.google_drive import GoogleDriveError
from app.modules.integrations.schemas import DriveUploadResultRead
from app.modules.network import service as network_service
from app.modules.organizations import service as organizations_service
from app.modules.support.service import actor_role_for

from app.modules.leads.service import LeadError

router = APIRouter(prefix="/contracts", tags=["contracts"])


async def _get_org_scoped_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID
) -> Contract:
    contract = await db.get(Contract, contract_id)
    if contract is None or contract.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found")
    return contract


async def _assert_own_contract_or_staff(
    db: AsyncSession, *, current_user: CurrentUser, contract: Contract
) -> None:
    if actor_role_for(current_user.roles) != "CUSTOMER":
        return
    customer_stmt = select(Customer.id).where(
        Customer.organization_id == current_user.organization_id, Customer.user_id == current_user.user_id
    )
    own_customer_id = (await db.execute(customer_stmt)).scalar_one_or_none()
    if own_customer_id is None or contract.customer_id != own_customer_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this contract")


@router.post("", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
async def create_contract(
    payload: ContractCreate,
    current_user: CurrentUser = Depends(require_permission("contracts.create")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    # The creator's role is frozen now since roles can change later. A
    # promoter here is acting for someone else, so their agent id is recorded
    # as activator; staff-created contracts get no such marker.
    created_by_role = actor_role_for(current_user.roles)
    activated_by_promoter_id = None
    if created_by_role == "PROMOTER":
        own_agent = await network_service.get_own_agent_profile(
            db, organization_id=current_user.organization_id, user_id=current_user.user_id
        )
        activated_by_promoter_id = own_agent.id if own_agent else None

    if payload.supply_point_id is None and await contract_service.product_requires_supply_point(
        db, product_version_id=payload.product_version_id
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Questo prodotto richiede un punto di fornitura (codice POD o PDR)."
        )
    try:
        contract = await contract_service.create_contract(
            db,
            organization_id=current_user.organization_id,
            customer_id=payload.customer_id,
            supply_point_id=payload.supply_point_id,
            product_version_id=payload.product_version_id,
            producer_agent_id=payload.producer_agent_id,
            lead_id=payload.lead_id,
            actor_user_id=current_user.user_id,
            correlation_id=str(uuid.uuid4()),
            notes=payload.notes,
            iban=payload.iban,
            email=payload.email,
            created_by_role=created_by_role,
            activated_by_promoter_id=activated_by_promoter_id,
        )
    except InvalidProducerAgentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except LeadError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.post("/mine", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
async def create_my_contract(
    payload: ContractSelfServiceCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    """Customer self-activation of an SOSNET product; authentication only, own
    account only (like POST /orders/mine). Creates supply point and contract
    and advances to DOCUMENTS_PENDING (service.py::create_contract_self_service)."""
    try:
        contract = await contract_service.create_contract_self_service(
            db,
            organization_id=current_user.organization_id,
            customer_user_id=current_user.user_id,
            product_version_id=payload.product_version_id,
            supply_point_payload=payload.supply_point,
            email=payload.email,
            holder_first_name=payload.holder_first_name,
            holder_last_name=payload.holder_last_name,
            pec=payload.pec,
            iban=payload.iban,
        )
    except SelfServiceContractError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except InvalidProducerAgentError as exc:
        # E.g. the referring promoter was deactivated; create_contract()
        # refuses non-ACTIVE producers. Surface it as a 400, not a 500.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.post("/for-customer", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
async def create_contract_for_my_customer(
    payload: ContractForCustomerCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    """A promoter activates a contract for one of their own customers (who
    may never have logged in). Authentication only; ownership of the customer
    is enforced in service.py::create_contract_for_recruited_customer."""
    try:
        contract = await contract_service.create_contract_for_recruited_customer(
            db, organization_id=current_user.organization_id, promoter_user_id=current_user.user_id,
            customer_id=payload.customer_id, product_version_id=payload.product_version_id,
            supply_point_payload=payload.supply_point, email=payload.email,
            holder_first_name=payload.holder_first_name, holder_last_name=payload.holder_last_name,
            pec=payload.pec, iban=payload.iban,
        )
    except SelfServiceContractError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except InvalidProducerAgentError as exc:
        # As in POST /contracts/mine.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.get("/mine/{contract_id}/payment-options", response_model=ContractPaymentOptionsRead)
async def get_my_contract_payment_options(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractPaymentOptionsRead:
    """Priced payment options for the caller's own contract, computed from
    the frozen amount; the client only picks a plan key."""
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    await _assert_own_contract_or_staff(db, current_user=current_user, contract=contract)

    card_available = await organizations_service.is_stripe_configured(
        db, organization_id=current_user.organization_id
    )
    payable = contract_service.is_payable(contract)
    version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
    cashback_percentage = int(version.contract_cashback_percentage or 0) if version is not None else 0
    options = (
        [
            ContractPaymentOptionRead(
                key=b.plan.key, label=b.plan.label, description=b.plan.description,
                instalments=b.plan.instalments, instalment_cents=b.instalment_cents,
                total_cents=b.total_cents, rounding_difference_cents=b.rounding_difference_cents,
                discount_percentage=b.discount_percentage, discount_cents=b.discount_cents,
            )
            for b in payment_plans.available_breakdowns(
                contract.gross_amount_cents or 0,
                full_payment_discount_percentage=await organizations_service.get_contract_full_payment_discount_percentage(
                    db, organization_id=current_user.organization_id
                ),
            )
        ]
        if payable
        else []
    )
    return ContractPaymentOptionsRead(
        contract_id=contract.id, payable=payable, status=contract.status,
        missing_amount=contract.status in contract_service.PREPAYABLE_STATUSES and not contract.gross_amount_cents,
        gross_amount_cents=contract.gross_amount_cents, card_available=card_available,
        options=options, paid_at=contract.paid_at, payment_plan=contract.payment_plan,
        cashback_percentage=cashback_percentage,
        cashback_total_cents=(
            pricing.contract_cashback_cents(version=version, gross_amount_cents=contract.gross_amount_cents)
            if version is not None and contract.gross_amount_cents
            else 0
        ),
    )


@router.post("/mine/{contract_id}/checkout-session")
async def create_my_contract_checkout_session(
    contract_id: uuid.UUID,
    payload: ContractCheckoutRequest,
    success_url: str,
    cancel_url: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Open Stripe Checkout for one's own contract, before or after document
    approval (service.py::PREPAYABLE_STATUSES). Returns the URL; only the
    verified webhook marks it paid."""
    from app.modules.payments import service as payments_service

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    await _assert_own_contract_or_staff(db, current_user=current_user, contract=contract)
    if contract.paid_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Questo contratto risulta già pagato.")
    if not contract_service.is_payable(contract):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Questo contratto non si può pagare in questo stato.")

    try:
        url = await payments_service.create_checkout_session_for_contract(
            db, organization_id=current_user.organization_id, contract=contract,
            plan_key=payload.payment_plan, success_url=success_url, cancel_url=cancel_url,
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except payments_service.PaymentsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"checkout_url": url}


@router.get("", response_model=list[ContractRead])
async def list_contracts(
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
    limit: int = 200,
) -> list[ContractRead]:
    stmt = (
        select(Contract)
        .where(Contract.organization_id == current_user.organization_id)
        .order_by(Contract.created_at.desc())
        .limit(limit)
    )
    contracts = (await db.execute(stmt)).scalars().all()
    rows = await contract_service.to_read_dicts(db, list(contracts))
    return [ContractRead(**row) for row in rows]


@router.get("/mine", response_model=list[ContractRead])
async def list_my_contracts(
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
) -> list[ContractRead]:
    """The caller's own contracts only; empty if no Customer row is linked."""
    customer_stmt = select(Customer.id).where(
        Customer.organization_id == current_user.organization_id,
        Customer.user_id == current_user.user_id,
    )
    customer_id = (await db.execute(customer_stmt)).scalar_one_or_none()
    if customer_id is None:
        return []

    stmt = (
        select(Contract)
        .where(Contract.organization_id == current_user.organization_id, Contract.customer_id == customer_id)
        .order_by(Contract.created_at.desc())
    )
    contracts = (await db.execute(stmt)).scalars().all()
    rows = await contract_service.to_read_dicts(db, list(contracts))
    return [ContractRead(**row) for row in rows]


@router.get("/{contract_id}", response_model=ContractRead)
async def get_contract(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.get("/{contract_id}/status-history", response_model=list[ContractStatusHistoryRead])
async def get_contract_status_history(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
) -> list[ContractStatusHistoryRead]:
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    await _assert_own_contract_or_staff(db, current_user=current_user, contract=contract)
    rows = await contract_service.get_status_history(db, contract_id=contract_id)
    return [ContractStatusHistoryRead(**row) for row in rows]


@router.patch("/{contract_id}/iban", response_model=ContractRead)
async def update_contract_iban(
    contract_id: uuid.UUID,
    payload: ContractIbanUpdate,
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    await _assert_own_contract_or_staff(db, current_user=current_user, contract=contract)
    contract = await contract_service.set_contract_iban(
        db, organization_id=current_user.organization_id, contract=contract,
        iban=payload.iban, actor_user_id=current_user.user_id,
    )
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


#: Targets on the path to first activation. Any of them can cascade to ACTIVE
#: (a paid contract goes APPROVED -> ACTIVE), which releases commissions, so
#: all require an accepted commission preview. Reactivation from SUSPENDED
#: pays nothing and is not gated.
_ACTIVATION_PATH_TARGETS = frozenset({"APPROVED", "PAYMENT_PENDING", "PAID", "ACTIVATION_PENDING", "ACTIVE"})


@router.get("/{contract_id}/commission-preview")
async def get_commission_preview(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Who would be paid what, and when, if the contract activated now.
    Read-only (commissions/services/preview.py)."""
    from app.modules.commissions.services.preview import build_commission_preview

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    if contract.product_version_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Questo punto non ha ancora un pacchetto: non ci sono provvigioni da mostrare."
        )
    preview = await build_commission_preview(db, organization_id=current_user.organization_id, contract=contract)
    preview["already_accepted"] = await contract_service.has_accepted_commission_plan(db, contract_id=contract.id)
    return preview


@router.get("/{contract_id}/commission-log")
async def get_commission_log(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accepted preview, instalment releases and actual commission movements
    side by side, to verify the outcome matches what was approved."""
    from app.modules.commissions.services import admin_ledger
    from app.modules.contracts import instalments as instalments_service
    from app.modules.contracts.models import ContractCommissionPlan
    from app.modules.users.models import User

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    plan = (
        await db.execute(select(ContractCommissionPlan).where(ContractCommissionPlan.contract_id == contract.id))
    ).scalar_one_or_none()
    accepted_by = await db.get(User, plan.accepted_by_user_id) if plan is not None else None
    rows = await instalments_service.list_instalments(db, contract_id=contract.id)
    confirmer_ids = {r.confirmed_by_user_id for r in rows if r.confirmed_by_user_id}
    confirmers = {
        u.id: u.email for u in (await db.execute(select(User).where(User.id.in_(confirmer_ids)))).scalars()
    } if confirmer_ids else {}
    movements = await admin_ledger.get_commission_movements(
        db, organization_id=current_user.organization_id, contract_id=contract.id
    )
    return {
        "contract_id": str(contract.id),
        "status": contract.status,
        "payment_plan": contract.payment_plan,
        "accepted_plan": (
            {
                "accepted_at": plan.accepted_at.isoformat(),
                "accepted_by": accepted_by.email if accepted_by else None,
                "total_commission_cents": plan.total_commission_cents,
                "preview": plan.preview,
            }
            if plan is not None
            else None
        ),
        "instalments": [
            {
                "number": r.number,
                "instalments_total": r.instalments_total,
                "due_date": r.due_date.isoformat(),
                "amount_cents": r.amount_cents,
                "status": r.status,
                "paid_at": r.paid_at.isoformat() if r.paid_at else None,
                "payment_source": r.payment_source,
                "confirmed_by": confirmers.get(r.confirmed_by_user_id) if r.confirmed_by_user_id else None,
                "commission_released_at": r.commission_released_at.isoformat() if r.commission_released_at else None,
                "commission_pending": r.commission_event_id is not None and r.commission_released_at is None,
            }
            for r in rows
        ],
        "movements": [
            {
                "id": str(m["id"]),
                "agent_name": m["agent_name"],
                "movement_type": m["movement_type"],
                "amount_cents": m["amount_cents"],
                "status": m["status"],
                "explanation": m["explanation"],
                "effective_date": m["effective_date"].isoformat(),
            }
            for m in movements
        ],
    }


@router.post("/{contract_id}/instalments/{number}/confirm")
async def confirm_instalment_manually(
    contract_id: uuid.UUID,
    number: int,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Staff confirmation of an instalment Stripe did not collect; releases
    its commissions if the contract is active."""
    from app.modules.contracts import instalments as instalments_service

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    try:
        row = await instalments_service.confirm_manually(
            db, contract=contract, number=number, actor_user_id=current_user.user_id
        )
    except instalments_service.InstalmentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await audit_service.record(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        action="contract.instalment_confirmed_manually", entity_type="contract", entity_id=str(contract.id),
        new_value={"instalment_number": number},
    )
    await db.commit()
    # Earns cashback like a Stripe-collected instalment; keyed by instalment
    # number so a later Stripe retry cannot credit it twice.
    await contract_service.credit_contract_instalment_cashback(
        db, organization_id=current_user.organization_id, contract=contract, instalment_number=row.number
    )
    return {"number": row.number, "status": row.status}


@router.post("/{contract_id}/stop-billing", response_model=ContractRead)
async def stop_contract_billing(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    """Stop recurring Stripe billing for this contract; in a multi-contract
    subscription only its item is removed."""
    from app.modules.payments import service as payments_service

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    try:
        contract = await payments_service.stop_contract_billing(
            db, organization_id=current_user.organization_id, contract=contract, actor_user_id=current_user.user_id
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except payments_service.PaymentsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.post("/{contract_id}/transition", response_model=ContractRead)
async def transition_contract(
    contract_id: uuid.UUID,
    payload: ContractTransitionRequest,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    if (
        payload.to_status in _ACTIVATION_PATH_TARGETS
        and contract.activated_at is None
        and contract.status != "SUSPENDED"
        and not await contract_service.has_accepted_commission_plan(db, contract_id=contract.id)
    ):
        if not payload.accept_commission_preview_checksum:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Prima di approvare devi controllare e accettare l'anteprima delle provvigioni.",
            )
        try:
            await contract_service.accept_commission_plan(
                db, organization_id=current_user.organization_id, contract=contract,
                checksum=payload.accept_commission_preview_checksum, actor_user_id=current_user.user_id,
            )
        except contract_service.CommissionPreviewChangedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    try:
        contract = await contract_service.transition_contract(
            db,
            organization_id=current_user.organization_id,
            contract=contract,
            to_status=payload.to_status,
            actor_user_id=current_user.user_id,
            reason=payload.reason,
            notes=payload.notes,
            correlation_id=str(uuid.uuid4()),
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.get("/{contract_id}/dossier.zip")
async def download_contract_dossier(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("documents.review")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """All contract attachments plus a summary PDF as
    `<customer name>-<contract id>.zip`.

    Requires `documents.review`, not `documents.download` (which customers
    also hold): the dossier includes personal data, IBAN and payment
    references.

    Built in memory so no plaintext copy of identity documents lands on disk."""
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    built = await dossier.build_dossier(
        db, organization_id=current_user.organization_id, contract=contract
    )
    await audit_service.record(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        action="contract.dossier_downloaded", entity_type="contract", entity_id=str(contract_id),
        new_value={"files": len(built.files), "archive": built.zip_filename},
    )
    await db.commit()

    content = dossier.zip_bytes(built)
    # ASCII `filename=` for legacy clients, RFC 5987 `filename*=` so
    # non-ASCII names survive.
    ascii_name = built.zip_filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    quoted = urllib.parse.quote(built.zip_filename)
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}',
            "Content-Length": str(len(content)),
        },
    )


@router.post("/{contract_id}/dossier/drive", response_model=DriveUploadResultRead)
async def send_contract_dossier_to_drive(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("documents.review")),
    db: AsyncSession = Depends(get_db),
) -> DriveUploadResultRead:
    """Upload the same dossier as the zip to a Google Drive folder named
    `<customer name>-<contract id>`."""
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    built = await dossier.build_dossier(
        db, organization_id=current_user.organization_id, contract=contract
    )
    try:
        result = await google_drive.upload_dossier(
            db, organization_id=current_user.organization_id, dossier=built
        )
    except GoogleDriveError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_service.record(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        action="contract.dossier_sent_to_drive", entity_type="contract", entity_id=str(contract_id),
        new_value={"folder": result.folder_name, "uploaded": result.uploaded, "replaced": result.replaced},
    )
    await db.commit()

    return DriveUploadResultRead(
        folder_name=result.folder_name,
        folder_url=result.folder_url,
        uploaded=result.uploaded,
        replaced=result.replaced,
    )
