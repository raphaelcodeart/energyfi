import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db, utcnow
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.foundation.rate_limit import rate_limit
from app.foundation.storage import UploadValidationError, upload_media
from app.modules.customers.schemas import CustomerCreate, CustomerRead
from app.modules.network import collaboration_documents
from app.modules.network import service as network_service
from app.modules.network.models import AgentProfile
from app.modules.network.schemas import (
    AgentCreateRequest,
    AgentListItemRead,
    AgentLookupRead,
    AgentPageRead,
    AgentProfileRead,
    AgentRejectRequest,
    AgentUpdateRequest,
    BranchContractRead,
    BranchMemberRead,
    BranchSummaryRead,
    CollaborationDocumentRead,
    MoveAgentRequest,
    OrganizationNetworkLevelsRead,
    PromoterApplicationRequest,
    RankProgressRead,
    RecruitRequest,
    RootPromoterCreateRequest,
    RootPromoterCreateResponse,
)
from app.modules.notifications import service as notifications_service
from app.modules.referral.schemas import PromoterCodeRead

router = APIRouter(prefix="/network", tags=["network"])


async def _resolve_own_agent_id(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID | None:
    stmt = select(AgentProfile.id).where(
        AgentProfile.organization_id == organization_id, AgentProfile.user_id == user_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


# Roles holding network.manage (see rbac/models.py DEFAULT_ROLE_PERMISSIONS):
# org-wide network visibility, so the branch-ownership check is skipped.
# Includes ADMIN, which already sees the whole network via GET /network/agents.
_BRANCH_ACCESS_BYPASS_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN", "SALES_MANAGER"}

# Roles that still see FROZEN members (and their subtrees) in a branch. For
# everyone else, SALES_MANAGER included, frozen members are fully detached
# from the network view. Deliberately narrower than
# _BRANCH_ACCESS_BYPASS_ROLES: seeing every branch and seeing frozen people
# are separate privileges.
_FROZEN_VISIBLE_ROLES = {"SUPER_ADMIN", "ORGANIZATION_ADMIN", "ADMIN"}


def _may_see_frozen(current_user: CurrentUser) -> bool:
    return bool(_FROZEN_VISIBLE_ROLES & set(current_user.roles))


async def _assert_branch_access(
    db: AsyncSession, *, current_user: CurrentUser, agent_id: uuid.UUID
) -> None:
    """ABAC check on top of the RBAC gate: a promoter may read only a branch
    rooted at themselves or one of their descendants. Roles with org-wide
    network.manage skip it."""
    if _BRANCH_ACCESS_BYPASS_ROLES & set(current_user.roles):
        return
    requesting_agent_id = await _resolve_own_agent_id(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    if requesting_agent_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No agent profile for this user")
    if requesting_agent_id != agent_id:
        authorized = await network_service.is_ancestor(
            db,
            organization_id=current_user.organization_id,
            ancestor_agent_id=requesting_agent_id,
            agent_id=agent_id,
        )
        if not authorized:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this branch")


@router.get("/mine", response_model=AgentProfileRead | None)
async def get_my_agent_profile(
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead | None:
    """Resolve the caller's own agent_id; the dashboard calls this before
    /agents/{id}/branch."""
    from app.modules.commissions.models import Rank

    stmt = (
        select(AgentProfile, Rank.code)
        .join(Rank, Rank.id == AgentProfile.current_rank_id, isouter=True)
        .where(
            AgentProfile.organization_id == current_user.organization_id,
            AgentProfile.user_id == current_user.user_id,
        )
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    agent, rank_code = row
    return AgentProfileRead(
        id=agent.id,
        organization_id=agent.organization_id,
        user_id=agent.user_id,
        display_name=agent.display_name,
        promoter_code=agent.promoter_code,
        status=agent.status,
        photo_url=agent.photo_url,
        current_rank_id=agent.current_rank_id,
        rank_code=rank_code,
        rejection_reason=agent.rejection_reason,
        is_blacklisted=agent.is_blacklisted,
        collaboration_accepted_at=agent.collaboration_accepted_at,
    )


@router.get("/agents/me", response_model=AgentProfileRead | None)
async def get_my_promoter_application(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead | None:
    """The caller's 'Lavora con noi' application/agent profile and status, for
    any authenticated user (no network.* permission). Drives the customer-area
    card states: none / pending / rejected / active."""
    agent = await network_service.get_own_agent_profile(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    if agent is None:
        return None
    return AgentProfileRead.model_validate(agent)


@router.get("/agents/apply/documents", response_model=list[CollaborationDocumentRead])
async def get_collaboration_documents(
    _current_user: CurrentUser = Depends(get_current_user),
) -> list[CollaborationDocumentRead]:
    """Documents a customer must accept to become a promoter, with current
    versions.

    Served by the backend so the legally binding text has a single versioned
    copy, tied to the acceptance record, and can change without a frontend
    release. The dashboard renders one panel and checkbox per entry and sends
    the versions back on submit. Requires authentication only."""
    return [
        CollaborationDocumentRead(
            key=doc.key, version=doc.version, title=doc.title, subtitle=doc.subtitle,
            acceptance_label=doc.acceptance_label, blocks=doc.blocks,
        )
        for doc in collaboration_documents.COLLABORATION_DOCUMENTS
    ]


@router.post(
    "/agents/apply/request-otp",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("promoter-apply-otp", max_requests=5, window_seconds=300))],
)
async def request_promoter_application_otp(
    current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """Email the OTP that the 'Lavora con noi' confirmation step asks for;
    verified by POST /agents/apply."""
    from app.modules.auth import service as auth_service
    from app.modules.users.models import User

    user = await db.get(User, current_user.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    await auth_service.request_otp(
        db, user=user, purpose=auth_service.PROMOTER_APPLICATION_OTP_PURPOSE,
        context_line="Usa questo codice per confermare la tua richiesta 'Lavora con noi' e accettare il contratto di collaborazione.",
    )
    return {"ok": True}


@router.post("/agents/apply", response_model=AgentProfileRead, status_code=status.HTTP_201_CREATED)
async def apply_as_promoter(
    payload: PromoterApplicationRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    """'Lavora con noi': an existing CUSTOMER applies to become a PROMOTER.

    Not permission-gated, since a plain CUSTOMER holds no network.* permission
    and this is the self-service entry point. Requires accepting the
    collaboration documents and a valid OTP from POST /agents/apply/request-otp.
    Activation rules are in network/service.py::apply_as_promoter."""
    if "CUSTOMER" not in current_user.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only customers can apply to become a promoter")

    first_name, last_name = payload.first_name, payload.last_name
    if not first_name and not last_name:
        from app.modules.customers.models import Company, Customer, CustomerProfile
        from app.modules.customers.service import COMPANY_LIKE_KINDS

        customer = (
            await db.execute(
                select(Customer).where(
                    Customer.organization_id == current_user.organization_id,
                    Customer.user_id == current_user.user_id,
                )
            )
        ).scalar_one_or_none()
        if customer is not None:
            if customer.kind in COMPANY_LIKE_KINDS:
                company = await db.get(Company, customer.id)
                first_name, last_name = (company.company_name if company else None), ""
            else:
                profile = await db.get(CustomerProfile, customer.id)
                if profile is not None:
                    first_name, last_name = profile.first_name, profile.last_name
    first_name = first_name or "Promoter"
    last_name = last_name or ""

    try:
        agent = await network_service.apply_as_promoter(
            db, organization_id=current_user.organization_id,
            user_id=current_user.user_id, first_name=first_name, last_name=last_name,
            accept_contract=payload.accept_contract, otp_code=payload.otp_code,
            accepted_documents=payload.accepted_documents,
        )
    except network_service.DuplicateApplicationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except network_service.ContractNotAcceptedError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except network_service.InvalidOtpError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await notifications_service.notify_roles(
        db, organization_id=current_user.organization_id, roles=notifications_service.APPROVAL_NOTIFY_ROLES,
        type_="PROMOTER_APPROVAL_REQUESTED", entity_type="agent_profile", entity_id=agent.id,
        title=f"Nuova richiesta 'Lavora con noi': {agent.display_name}",
        body=f"Cliente esistente -- codice {agent.promoter_code} in attesa di approvazione.",
        exclude_user_id=current_user.user_id,
    )
    await db.commit()
    return AgentProfileRead.model_validate(agent)


@router.get("/agents/{agent_id}/branch", response_model=list[BranchMemberRead])
async def get_branch(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list[BranchMemberRead]:
    await _assert_branch_access(db, current_user=current_user, agent_id=agent_id)
    branch = await network_service.get_branch(
        db, organization_id=current_user.organization_id, root_agent_id=agent_id,
        include_frozen=_may_see_frozen(current_user),
    )
    return [BranchMemberRead(**row) for row in branch]


@router.get("/agents/{agent_id}/rank-progress", response_model=RankProgressRead)
async def get_rank_progress(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> RankProgressRead:
    """Progress toward the next legacy rank's thresholds (see
    commissions/services/rank_progress.py). Same branch-ownership rule as
    /branch."""
    from app.modules.commissions.services.rank_progress import (
        get_rank_progress as compute_rank_progress,
    )

    await _assert_branch_access(db, current_user=current_user, agent_id=agent_id)
    progress = await compute_rank_progress(db, organization_id=current_user.organization_id, agent_id=agent_id)
    return RankProgressRead(**progress.__dict__)


@router.get("/agents/{agent_id}/branch-summary", response_model=BranchSummaryRead)
async def get_branch_summary(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> BranchSummaryRead:
    """Per-agent contract/commission rollup for a promoter's downline (the
    "azienda" view). Same branch-ownership rule as /branch."""
    await _assert_branch_access(db, current_user=current_user, agent_id=agent_id)
    summary = await network_service.get_branch_summary(
        db, organization_id=current_user.organization_id, root_agent_id=agent_id,
        include_frozen=_may_see_frozen(current_user),
    )
    return BranchSummaryRead(**summary)


@router.get("/agents/me/companies")
async def get_my_companies(
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """The companies the caller can work with, whether they joined each one,
    and their results with its products."""
    from app.modules.network import card

    agent_id = await _resolve_own_agent_id(db, organization_id=current_user.organization_id, user_id=current_user.user_id)
    if agent_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessun profilo collaboratore per questo account.")
    return await card.get_my_companies(db, organization_id=current_user.organization_id, agent_id=agent_id)


@router.post("/agents/me/companies/{company_id}/{action}", status_code=status.HTTP_204_NO_CONTENT)
async def change_my_company_membership(
    company_id: uuid.UUID,
    action: str,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """`join` takes part in a company's plans, `leave` stops."""
    from app.modules.network import card

    if action not in ("join", "leave"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Azione non valida.")
    agent_id = await _resolve_own_agent_id(db, organization_id=current_user.organization_id, user_id=current_user.user_id)
    if agent_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessun profilo collaboratore per questo account.")
    try:
        await card.set_membership(
            db, organization_id=current_user.organization_id, agent_id=agent_id, company_id=company_id,
            join=action == "join",
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/companies/{company_id}/participants")
async def get_company_participants(
    company_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Staff view: collaborators who joined a company, those who sell its
    products without joining, and its customers."""
    from app.modules.network import card

    result = await card.get_company_participants(db, organization_id=current_user.organization_id, company_id=company_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Azienda non trovata.")
    return result


@router.get("/agents/me/plans")
async def get_my_plans(
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The Split Plans the caller works with, what each product would pay
    them today, and what each plan has paid them so far."""
    from app.modules.network import card

    agent_id = await _resolve_own_agent_id(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    if agent_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nessun profilo collaboratore per questo account.")
    return await card.get_my_plans(db, organization_id=current_user.organization_id, agent_id=agent_id)


@router.get("/agents/{agent_id}/product-network/{product_id}")
async def get_product_network(
    agent_id: uuid.UUID,
    product_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """A collaborator's network filtered to the people who bought one product,
    down to the depth its company reaches. Same access rule as /branch."""
    from app.modules.network import card

    await _assert_branch_access(db, current_user=current_user, agent_id=agent_id)
    result = await card.get_product_network(
        db, organization_id=current_user.organization_id, agent_id=agent_id, product_id=product_id
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prodotto non trovato.")
    return result


@router.get("/agents/{agent_id}/card")
async def get_agent_card(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Everything about one collaborator for the page opened from the tree:
    position, network below, sales, earnings by state, month and Split Plan.
    Same branch-ownership rule as /branch; the email only for staff."""
    from app.modules.network import card

    await _assert_branch_access(db, current_user=current_user, agent_id=agent_id)
    result = await card.get_agent_card(
        db, organization_id=current_user.organization_id, agent_id=agent_id,
        include_contact=bool(_BRANCH_ACCESS_BYPASS_ROLES & set(current_user.roles)),
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collaboratore non trovato.")
    return result


@router.get("/agents/{agent_id}/branch-contracts", response_model=list[BranchContractRead])
async def get_branch_contracts(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.read_branch")),
    db: AsyncSession = Depends(get_db),
) -> list[BranchContractRead]:
    """Contract-level detail (customer, product, status, commission) for a
    promoter's whole downline."""
    await _assert_branch_access(db, current_user=current_user, agent_id=agent_id)
    viewer_agent_id = await _resolve_own_agent_id(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    rows = await network_service.get_branch_contracts(
        db, organization_id=current_user.organization_id, root_agent_id=agent_id, viewer_agent_id=viewer_agent_id
    )
    return [BranchContractRead(**row) for row in rows]


@router.get("/organization/levels", response_model=OrganizationNetworkLevelsRead)
async def get_organization_network_levels(
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> OrganizationNetworkLevelsRead:
    """Organization-wide network depth and headcount (network.manage only)."""
    result = await network_service.get_organization_network_levels(db, organization_id=current_user.organization_id)
    return OrganizationNetworkLevelsRead(**result)


@router.get("/agents", response_model=list[AgentListItemRead])
async def list_agents(
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[AgentListItemRead]:
    """Org-wide agent registry for the admin 'Promoter' screen (network.manage)."""
    rows = await network_service.list_agents(db, organization_id=current_user.organization_id)
    return [AgentListItemRead(**row) for row in rows]


@router.get("/agents/page", response_model=AgentPageRead)
async def list_agents_page(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=network_service.MAX_AGENT_PAGE_SIZE),
    search: str | None = Query(None, max_length=120),
    status_filter: str | None = Query(None, alias="status", max_length=32),
    sort: str = Query("recent", pattern="^(recent|oldest|name|code)$"),
    parent_id: uuid.UUID | None = None,
    blacklisted: bool | None = None,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> AgentPageRead:
    """One page of the registry, filtered and counted on the server: the
    admin screens never download the whole network."""
    out = await network_service.list_agents_page(
        db, organization_id=current_user.organization_id, page=page, page_size=page_size, search=search,
        status=status_filter, sort=sort, parent_id=parent_id, blacklisted=blacklisted,
    )
    return AgentPageRead(**out)


@router.get("/agents/lookup", response_model=list[AgentLookupRead])
async def lookup_agents(
    q: str | None = Query(None, max_length=120),
    ids: str | None = Query(None, max_length=8000, description="Comma-separated agent ids"),
    status_filter: str | None = Query(None, alias="status", max_length=32),
    limit: int = Query(20, ge=1, le=50),
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[AgentLookupRead]:
    """Quick search for the "choose a collaborator" fields, or the names of
    the ids given (same permission as the full registry it replaces)."""
    try:
        id_list = [uuid.UUID(x) for x in ids.split(",") if x.strip()] if ids else None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Id non valido") from exc
    rows = await network_service.lookup_agents(
        db, organization_id=current_user.organization_id, q=q, ids=id_list, status=status_filter, limit=limit)
    return [AgentLookupRead(**r) for r in rows]


@router.get("/agents/export.csv")
async def export_agents_csv(
    search: str | None = Query(None, max_length=120),
    status_filter: str | None = Query(None, alias="status", max_length=32),
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """The filtered registry as CSV, streamed (the whole network included)."""
    import csv
    import io

    async def rows():
        buf = io.StringIO()
        writer = csv.writer(buf)
        buf.write("\ufeff")
        writer.writerow(["ID", "Nome", "Codice", "Ruolo commerciale", "Sponsor", "Stato", "Iscritto il"])
        async for row in network_service.iter_agents_csv(
                db, organization_id=current_user.organization_id, search=search, status=status_filter):
            writer.writerow(row)
            if buf.tell() > 64_000:
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()
        yield buf.getvalue()

    name = f"collaboratori_{utcnow().date().isoformat()}.csv"
    return StreamingResponse(rows(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/agents/{agent_id}/referral-link", response_model=PromoterCodeRead)
async def get_agent_referral_link(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> PromoterCodeRead:
    """Admin counterpart of GET /referral/mine: open any agent's personal link,
    e.g. to send it again. Same lazy get-or-create."""
    from app.modules.referral import service as referral_service

    try:
        promoter_code = await referral_service.get_or_create_promoter_code(
            db, organization_id=current_user.organization_id, agent_id=agent_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found") from exc
    return PromoterCodeRead.model_validate(promoter_code)


@router.post("/agents", response_model=AgentProfileRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreateRequest,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    """An ADMIN can only suggest a new promoter: it is created PENDING_APPROVAL
    and cannot produce contracts until a network.approve holder approves it via
    PATCH /agents/{id}/approve.

    payload.customer_email optionally links an existing customer login; approval
    then adds the PROMOTER role to that user's existing roles."""
    from app.modules.users.models import User

    user_id = None
    if payload.customer_email:
        user = (
            await db.execute(
                select(User).where(
                    User.organization_id == current_user.organization_id,
                    func.lower(User.email) == payload.customer_email.lower(),
                )
            )
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
        existing_agent = await network_service.get_own_agent_profile(
            db, organization_id=current_user.organization_id, user_id=user.id
        )
        if existing_agent is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"This user already has a promoter profile ({existing_agent.status})"
            )
        user_id = user.id

    try:
        agent = await network_service.create_agent(
            db,
            organization_id=current_user.organization_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            promoter_code=payload.promoter_code,
            parent_agent_id=payload.parent_agent_id,
            current_rank_id=payload.current_rank_id,
            commercial_role_id=payload.commercial_role_id,
            actor_user_id=current_user.user_id,
            user_id=user_id,
            status="PENDING_APPROVAL",
        )
    except network_service.NetworkError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await notifications_service.notify_roles(
        db, organization_id=current_user.organization_id, roles=notifications_service.APPROVAL_NOTIFY_ROLES,
        type_="PROMOTER_APPROVAL_REQUESTED", entity_type="agent_profile", entity_id=agent.id,
        title=f"Nuovo promoter suggerito: {agent.display_name}",
        body=f"Codice {agent.promoter_code} in attesa di approvazione.",
        exclude_user_id=current_user.user_id,
    )
    await db.commit()
    return AgentProfileRead.model_validate(agent)


@router.post("/agents/root", response_model=RootPromoterCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_root_promoter(
    payload: RootPromoterCreateRequest,
    current_user: CurrentUser = Depends(require_permission("network.approve")),
    db: AsyncSession = Depends(get_db),
) -> RootPromoterCreateResponse:
    """Create a new parentless network root with login and referral link in one
    step. Requires network.approve because it bypasses suggest-then-approve;
    it is the only way to start a new independent branch."""
    try:
        agent, user, promoter_code_row, temporary_password = await network_service.create_root_promoter_with_login(
            db,
            organization_id=current_user.organization_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            promoter_code=payload.promoter_code,
            actor_user_id=current_user.user_id,
        )
    except network_service.RootPromoterConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return RootPromoterCreateResponse(
        agent_id=agent.id,
        display_name=agent.display_name,
        promoter_code=agent.promoter_code,
        personal_link=promoter_code_row.personal_link,
        email=user.email,
        temporary_password=temporary_password,
    )


@router.patch("/agents/{agent_id}", response_model=AgentProfileRead)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    try:
        agent = await network_service.update_agent(
            db,
            organization_id=current_user.organization_id,
            agent_id=agent_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            status_value=payload.status,
            current_rank_id=payload.current_rank_id,
            actor_user_id=current_user.user_id,
            is_blacklisted=payload.is_blacklisted,
        )
    except network_service.AgentApprovalError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return AgentProfileRead.model_validate(agent)


@router.post("/agents/{agent_id}/photo", response_model=AgentProfileRead)
async def upload_agent_photo(
    agent_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    file_bytes = await file.read()
    try:
        photo_url = upload_media(
            file_bytes=file_bytes, content_type=file.content_type or "", key_prefix="photos/promoters"
        )
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    agent = await network_service.set_agent_photo(
        db, organization_id=current_user.organization_id, agent_id=agent_id,
        photo_url=photo_url, actor_user_id=current_user.user_id,
    )
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return AgentProfileRead.model_validate(agent)


@router.post("/agents/recruit", response_model=AgentProfileRead, status_code=status.HTTP_201_CREATED)
async def recruit_agent(
    payload: RecruitRequest,
    current_user: CurrentUser = Depends(require_permission("network.recruit")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    """A promoter proposes a new direct collaborator under themselves only;
    placing an agent elsewhere requires network.manage or a move request. The
    agent is created PENDING_APPROVAL, like POST /agents."""
    own_agent_id = await _resolve_own_agent_id(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    if own_agent_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No agent profile for this user")

    try:
        agent = await network_service.create_agent(
            db,
            organization_id=current_user.organization_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            promoter_code=payload.promoter_code,
            parent_agent_id=own_agent_id,
            current_rank_id=payload.current_rank_id,
            actor_user_id=current_user.user_id,
            status="PENDING_APPROVAL",
        )
    except network_service.NetworkError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await notifications_service.notify_roles(
        db, organization_id=current_user.organization_id, roles=notifications_service.APPROVAL_NOTIFY_ROLES,
        type_="PROMOTER_APPROVAL_REQUESTED", entity_type="agent_profile", entity_id=agent.id,
        title=f"Nuovo collaboratore suggerito: {agent.display_name}",
        body=f"Reclutato da un promoter -- codice {agent.promoter_code} in attesa di approvazione.",
    )
    await db.commit()
    return AgentProfileRead.model_validate(agent)


@router.patch("/agents/{agent_id}/approve", response_model=AgentProfileRead)
async def approve_agent(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("network.approve")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    try:
        agent = await network_service.approve_agent(
            db, organization_id=current_user.organization_id, agent_id=agent_id, actor_user_id=current_user.user_id
        )
    except network_service.AgentApprovalError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")

    if agent.user_id is not None:
        await notifications_service.notify_user(
            db, organization_id=current_user.organization_id, user_id=agent.user_id,
            type_="PROMOTER_APPROVED", entity_type="agent_profile", entity_id=agent.id,
            title="Il tuo profilo promoter è stato approvato",
            body=f"{agent.display_name} ({agent.promoter_code}) è ora attivo.",
        )
        await db.commit()
    return AgentProfileRead.model_validate(agent)


@router.patch("/agents/{agent_id}/reject", response_model=AgentProfileRead)
async def reject_agent(
    agent_id: uuid.UUID,
    payload: AgentRejectRequest,
    current_user: CurrentUser = Depends(require_permission("network.approve")),
    db: AsyncSession = Depends(get_db),
) -> AgentProfileRead:
    try:
        agent = await network_service.reject_agent(
            db, organization_id=current_user.organization_id, agent_id=agent_id,
            actor_user_id=current_user.user_id, reason=payload.reason,
        )
    except network_service.AgentApprovalError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")

    if agent.user_id is not None:
        await notifications_service.notify_user(
            db, organization_id=current_user.organization_id, user_id=agent.user_id,
            type_="PROMOTER_REJECTED", entity_type="agent_profile", entity_id=agent.id,
            title="Il tuo profilo promoter suggerito non è stato approvato",
            body=payload.reason,
        )
        await db.commit()
    return AgentProfileRead.model_validate(agent)


@router.post("/agents/{agent_id}/move", status_code=status.HTTP_204_NO_CONTENT)
async def move_agent(
    agent_id: uuid.UUID,
    payload: MoveAgentRequest,
    current_user: CurrentUser = Depends(require_permission("network.manage")),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await network_service.move_agent(
            db,
            organization_id=current_user.organization_id,
            agent_id=agent_id,
            new_parent_agent_id=payload.new_parent_agent_id,
            requested_by=current_user.user_id,
            approved_by=current_user.user_id,  # placeholder self-approval, see open-questions.md #2
            reason=payload.reason,
            effective_at=payload.effective_at,
        )
    except network_service.CycleError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except network_service.NetworkError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_recruited_customer(
    payload: CustomerCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerRead:
    """"Miei Clienti": a promoter registers a new customer, attributed to them as
    with a referral-link signup. Only authentication is required; the service
    checks for an ACTIVE AgentProfile (same trust model as /contracts/mine)."""
    try:
        customer = await network_service.create_recruited_customer(
            db, organization_id=current_user.organization_id, promoter_user_id=current_user.user_id,
            payload=payload, actor_user_id=current_user.user_id,
        )
    except network_service.RecruitedCustomerError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    from app.modules.customers import service as customers_service

    row = await customers_service.get_customer_detail(
        db, organization_id=current_user.organization_id, customer_id=customer.id
    )
    return CustomerRead(**row)


@router.get("/customers/mine", response_model=list[CustomerRead])
async def list_my_recruited_customers(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerRead]:
    rows = await network_service.list_recruited_customers(
        db, organization_id=current_user.organization_id, promoter_user_id=current_user.user_id
    )
    return [CustomerRead(**row) for row in rows]
