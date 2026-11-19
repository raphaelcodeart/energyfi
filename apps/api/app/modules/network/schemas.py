import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.foundation.normalization import normalize_email, normalize_person_name


class AgentProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    display_name: str
    promoter_code: str
    status: str
    photo_url: str | None = None
    current_rank_id: uuid.UUID | None
    rank_code: str | None = None
    #: Today's commercial role (history at /commercial/agents/{id}/roles).
    current_commercial_role_id: uuid.UUID | None = None
    rejection_reason: str | None = None
    is_blacklisted: bool = False
    collaboration_accepted_at: datetime | None = None
    #: {key: {"version": ..., "accepted_at": ...}}: accepted documents and
    #: wording. Empty when no per-document acceptance was recorded; never
    #: back-filled, since the log must not claim acceptance of unseen text.
    collaboration_accepted_documents: dict[str, dict] = {}


class RankProgressRead(BaseModel):
    current_rank_code: str | None
    current_rank_name: str | None
    next_rank_code: str | None
    next_rank_name: str | None
    is_max_rank: bool
    personal_volume_cents: int
    personal_volume_threshold_cents: int
    group_volume_cents: int
    group_volume_threshold_cents: int


class NetworkNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: uuid.UUID
    direct_parent_agent_id: uuid.UUID | None
    status: str


class BranchMemberRead(BaseModel):
    agent_id: uuid.UUID
    depth: int
    display_name: str
    promoter_code: str
    status: str
    rank_code: str | None
    role_code: str | None = None
    role_name: str | None = None
    # Direct parent within this branch; null for the root and for any parent
    # outside the fetch. Lets the frontend build the tree from real edges.
    parent_agent_id: uuid.UUID | None = None
    # The owner's account is frozen (users.status == FROZEN), independent of
    # `status`. Only admin-tier viewers ever see true; for others these rows
    # are filtered out server-side (network/service.py::get_branch).
    is_frozen: bool = False


class BranchAgentSummaryRead(BaseModel):
    agent_id: uuid.UUID
    depth: int
    display_name: str
    promoter_code: str
    status: str
    rank_code: str | None
    role_code: str | None = None
    role_name: str | None = None
    is_frozen: bool = False
    contracts_total: int
    contracts_by_status: dict[str, int]
    contracts_problem: int
    contracts_in_progress: int
    contracts_processed: int
    commission_cents: int


class BranchSummaryTotals(BaseModel):
    contracts: int
    commission_cents: int
    contracts_by_status: dict[str, int] = {}
    contracts_closed: int = 0
    contracts_rejected: int = 0
    contracts_pending: int = 0
    contracts_in_progress: int = 0
    levels_below: int = 0
    people_total: int = 0


class BranchSummaryRead(BaseModel):
    agents: list[BranchAgentSummaryRead]
    totals: BranchSummaryTotals


class BranchContractRead(BaseModel):
    contract_id: uuid.UUID
    status: str
    customer_id: uuid.UUID
    customer_name: str
    customer_email: str | None
    customer_phone: str | None
    product_name: str
    value_cents: int
    supply_point_label: str | None = None
    expires_at: datetime | None = None
    producer_agent_id: uuid.UUID
    producer_name: str
    commission_cents: int
    # The viewer's own commission on this contract; None (not 0) when the
    # viewer has no agent profile and so is never a beneficiary.
    my_commission_cents: int | None = None
    is_problem: bool
    admin_note: str | None = None


class MoveAgentRequest(BaseModel):
    new_parent_agent_id: uuid.UUID | None
    reason: str
    effective_at: datetime | None = None


class AgentListItemRead(BaseModel):
    id: uuid.UUID
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    promoter_code: str
    status: str
    photo_url: str | None = None
    current_rank_id: uuid.UUID | None
    rank_code: str | None
    commercial_role_id: uuid.UUID | None = None
    role_code: str | None = None
    role_name: str | None = None
    direct_parent_agent_id: uuid.UUID | None
    joined_at: datetime
    rejection_reason: str | None = None
    # None for agents without a login (AgentProfile.user_id is nullable).
    email: str | None = None
    is_blacklisted: bool = False
    user_id: uuid.UUID | None = None
    collaboration_accepted_at: datetime | None = None
    #: {key: {"version": ..., "accepted_at": ...}}: accepted documents and
    #: wording. Empty when no per-document acceptance was recorded; never
    #: back-filled, since the log must not claim acceptance of unseen text.
    collaboration_accepted_documents: dict[str, dict] = {}
    email_verified: bool = False
    privacy_accepted: bool = False
    user_status: str | None = None


class AgentPageItemRead(AgentListItemRead):
    parent_name: str | None = None
    parent_code: str | None = None
    direct_count: int = 0
    network_size: int = 0
    mamify_customer_id: str | None = None
    #: Login email, or the Mamify one for people without a login yet.
    contact_email: str | None = None


class AgentPageRead(BaseModel):
    items: list[AgentPageItemRead]
    total: int
    page: int
    page_size: int
    pages: int
    #: Whole organization, by status, plus ALL and BLACKLISTED.
    counts: dict[str, int]


class AgentLookupRead(BaseModel):
    id: uuid.UUID
    display_name: str
    promoter_code: str
    status: str
    user_id: uuid.UUID | None = None


class AgentCreateRequest(BaseModel):
    first_name: str
    last_name: str
    promoter_code: str
    parent_agent_id: uuid.UUID | None = None
    current_rank_id: uuid.UUID | None = None
    #: Initial commercial role; the organization default when omitted.
    commercial_role_id: uuid.UUID | None = None
    # Optionally links the new agent to an existing customer login instead of
    # creating a login-less suggestion.
    customer_email: EmailStr | None = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_name_fields(cls, v: object) -> object:
        return normalize_person_name(v) if isinstance(v, str) else v

    @field_validator("customer_email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: object) -> object:
        return normalize_email(v) if isinstance(v, str) else v

    @field_validator("promoter_code", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class RootPromoterCreateRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    # Auto-generated (initials + random suffix) when omitted.
    promoter_code: str | None = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_name_fields(cls, v: object) -> object:
        """Trim stray whitespace so it never reaches the login or referral
        code; names are stored uppercase (see normalize_person_name)."""
        return normalize_person_name(v) if isinstance(v, str) else v

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: object) -> object:
        return normalize_email(v) if isinstance(v, str) else v

    @field_validator("promoter_code", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class RootPromoterCreateResponse(BaseModel):
    agent_id: uuid.UUID
    display_name: str
    promoter_code: str
    personal_link: str
    email: str
    # Returned only in this response, never stored or logged in plaintext.
    # The admin passes it on and the promoter changes it at first login.
    temporary_password: str


class RecruitRequest(BaseModel):
    first_name: str
    last_name: str
    promoter_code: str
    current_rank_id: uuid.UUID | None = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_name_fields(cls, v: object) -> object:
        return normalize_person_name(v) if isinstance(v, str) else v

    @field_validator("promoter_code", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class PromoterApplicationRequest(BaseModel):
    # Optional: derived from the caller's Customer profile when omitted; the
    # UI never sends them.
    first_name: str | None = None
    last_name: str | None = None
    # Must be true: the form's agreement checkbox gates submission.
    accept_contract: bool = False
    # {document key: version shown}, one entry per document in
    # network/collaboration_documents.py, so the record states which text was
    # accepted. Missing or outdated versions are rejected.
    accepted_documents: dict[str, str] = {}
    # The 6-digit code emailed by POST /agents/apply/request-otp.
    otp_code: str

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_name_fields(cls, v: object) -> object:
        return normalize_person_name(v) if isinstance(v, str) else v

    @field_validator("otp_code", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class AgentUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    status: str | None = None
    current_rank_id: uuid.UUID | None = None
    # true blacklists (stronger than TERMINATED: a reapplication needs manual
    # approval), false lifts it, omitted leaves it unchanged.
    is_blacklisted: bool | None = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_name_fields(cls, v: object) -> object:
        return normalize_person_name(v) if isinstance(v, str) else v


class AgentRejectRequest(BaseModel):
    reason: str | None = None


class OrganizationNetworkLevelsRead(BaseModel):
    people_total: int
    levels_total: int
    people_by_level: dict[int, int]


class CollaborationDocumentRead(BaseModel):
    """One document a prospective promoter must accept. `blocks` is structured
    content (heading / paragraph / clause / bullets / table / signature), never
    markup; see network/collaboration_documents.py."""

    key: str
    version: str
    title: str
    subtitle: str
    acceptance_label: str
    blocks: list[dict]
