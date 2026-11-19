import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.foundation.storage import UploadValidationError, upload_media
from app.modules.customers import service as customer_service
from app.modules.customers.models import Customer
from app.modules.customers.schemas import (
    CustomerCreate,
    CustomerDetailRead,
    CustomerRead,
    CustomerUpdate,
    ReassignPromoterRequest,
    StaffCustomerCreate,
    SupplyPointCreate,
    SupplyPointRead,
    SupplyPointUpdate,
)
from app.modules.referral import service as referral_service

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerRead])
async def list_customers(
    current_user: CurrentUser = Depends(require_permission("customers.read")),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerRead]:
    rows = await customer_service.list_customers(db, organization_id=current_user.organization_id)
    return [CustomerRead(**row) for row in rows]


@router.get("/me", response_model=CustomerRead)
async def get_my_customer_record(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    """The caller's own customer record, resolved from the session;
    authentication only.

    The customer catalog uses it to show only products allowed for the
    customer's kind (privato/azienda, see
    catalog/pricing.py::product_allows_customer_kind). Staff accounts without a
    customer record get 404.

    Must stay above /{customer_id}: routes match in declaration order, and "me"
    would otherwise fail UUID validation with a 422.
    """
    own_id = (
        await db.execute(
            select(Customer.id).where(
                Customer.organization_id == current_user.organization_id,
                Customer.user_id == current_user.user_id,
            )
        )
    ).scalar_one_or_none()
    if own_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessuna anagrafica cliente collegata a questo account")
    # Reuse list_customers, narrowed to one row via `customer_ids`.
    rows = await customer_service.list_customers(
        db, organization_id=current_user.organization_id, customer_ids={own_id}
    )
    return CustomerRead(**rows[0])


@router.get("/{customer_id}", response_model=CustomerDetailRead)
async def get_customer(
    customer_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("customers.read")),
    db: AsyncSession = Depends(get_db),
) -> CustomerDetailRead:
    row = await customer_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer_id
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return CustomerDetailRead(**row)


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    current_user: CurrentUser = Depends(require_permission("customers.create")),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    try:
        customer = await customer_service.create_customer(
            db, organization_id=current_user.organization_id, payload=payload, actor_user_id=current_user.user_id
        )
    except customer_service.CustomerValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    row = await customer_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer.id
    )
    return CustomerRead(**row)


@router.post("/with-account", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer_with_account(
    payload: StaffCustomerCreate,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    """Staff "Nuovo cliente": personal data, login and set-your-password invite
    under the chosen promoter. Gated on customers.update because promoters hold
    customers.create but must not choose someone else's attribution."""
    from app.modules.network import service as network_service

    try:
        customer = await network_service.create_customer_with_account_by_staff(
            db, organization_id=current_user.organization_id, promoter_agent_id=payload.promoter_agent_id,
            payload=payload, actor_user_id=current_user.user_id,
        )
    except network_service.RecruitedCustomerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    row = await customer_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer.id
    )
    return CustomerRead(**row)


@router.post("/{customer_id}/account", response_model=CustomerRead)
async def create_customer_login(
    customer_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    """Give a login to a customer registered as personal data only and email
    the set-your-password invite."""
    from app.modules.network import service as network_service

    try:
        await network_service.create_login_for_existing_customer(
            db, organization_id=current_user.organization_id, customer_id=customer_id,
            actor_user_id=current_user.user_id,
        )
    except network_service.RecruitedCustomerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    row = await customer_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer_id
    )
    return CustomerRead(**row)


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    customer = await customer_service.update_customer(
        db,
        organization_id=current_user.organization_id,
        customer_id=customer_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    row = await customer_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer_id
    )
    return CustomerRead(**row)


@router.post("/{customer_id}/photo", response_model=CustomerRead)
async def upload_customer_photo(
    customer_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    file_bytes = await file.read()
    try:
        photo_url = upload_media(
            file_bytes=file_bytes, content_type=file.content_type or "", key_prefix="photos/customers"
        )
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    customer = await customer_service.set_customer_photo(
        db, organization_id=current_user.organization_id, customer_id=customer_id,
        photo_url=photo_url, actor_user_id=current_user.user_id,
    )
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    row = await customer_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer_id
    )
    return CustomerRead(**row)


@router.post("/{customer_id}/reassign-promoter", response_model=CustomerRead)
async def reassign_customer_promoter(
    customer_id: uuid.UUID,
    payload: ReassignPromoterRequest,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    """Admin-only: move a customer's attribution to another promoter. See
    referral_service.reassign_customer_promoter."""
    try:
        await referral_service.reassign_customer_promoter(
            db, organization_id=current_user.organization_id, customer_id=customer_id,
            new_agent_id=payload.new_agent_id, requested_by=current_user.user_id, reason=payload.reason,
        )
    except referral_service.ReassignmentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    row = await customer_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer_id
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return CustomerRead(**row)


@router.post("/{customer_id}/supply-points", response_model=SupplyPointRead, status_code=status.HTTP_201_CREATED)
async def add_supply_point(
    customer_id: uuid.UUID,
    payload: SupplyPointCreate,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> SupplyPointRead:
    supply_point = await customer_service.add_supply_point(
        db,
        organization_id=current_user.organization_id,
        customer_id=customer_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if supply_point is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return SupplyPointRead.model_validate(supply_point)


@router.patch("/supply-points/{supply_point_id}", response_model=SupplyPointRead)
async def update_supply_point(
    supply_point_id: uuid.UUID,
    payload: SupplyPointUpdate,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> SupplyPointRead:
    supply_point = await customer_service.update_supply_point(
        db,
        organization_id=current_user.organization_id,
        supply_point_id=supply_point_id,
        payload=payload,
        actor_user_id=current_user.user_id,
    )
    if supply_point is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supply point not found")
    return SupplyPointRead.model_validate(supply_point)
