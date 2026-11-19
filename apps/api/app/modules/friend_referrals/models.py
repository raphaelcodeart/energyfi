"""The "Invita un amico" network: one level, separate from the commercial network.

Every person with a login has a personal invite link and a flat list of who
signed up through it: no hierarchy, no closure table, **no commissions**. It
lets non-promoters see who they brought in and count how many activated a
contract.

It never decides who earns anything. Placement in the commercial tree stays
with the `referral`/`network` domains:

  - referrer IS a promoter  -> the customer joins the referrer's tree
  - referrer is NOT         -> the customer joins the tree under the
                               referrer's own promoter

so these tables could be dropped without changing any commission.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

#: Activated invitees per reward. Repeatable: 10, 20, 30 ... are each a
#: separately claimable milestone.
REWARD_EVERY = 10

#: SosnetCash credited to the referrer's wallet when staff confirm a reward.
REWARD_CENTS = 10_00

#: Reward description in customer-facing words, served to the dashboard so
#: every place showing it shares one value.
REWARD_DESCRIPTION = "un bonus di 10 € in cashback omaggio"

#: A referred customer is "attivo" once a contract is in force. RENEWED counts,
#: since a renewed contract is still active (docs/business-rules.md).
ACTIVE_CONTRACT_STATUSES = ("ACTIVE", "RENEWED")

#: Which kind of link was used; lets admins tell promoter recruiting from
#: customer word-of-mouth.
REFERRAL_SOURCE_PROMOTER_LINK = "PROMOTER_LINK"
REFERRAL_SOURCE_FRIEND_LINK = "FRIEND_LINK"

CLAIM_STATUSES = ("REQUESTED", "FULFILLED", "REJECTED")


class FriendReferralCode(UUIDPKMixin, TimestampMixin, Base):
    """One personal invite code per login, created lazily on first use.

    Kept apart from `promoter_codes`, which means "this agent earns on what
    comes through" and feeds attribution, the network tree and commissions.
    These codes pay nobody; mixing them in would skew every promoter-code query.
    """

    __tablename__ = "sn_friend_invite_codes"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_sn_friend_invite_codes_user_id"),
        UniqueConstraint("code", name="uq_sn_friend_invite_codes_code"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"))
    code: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")


class FriendReferral(UUIDPKMixin, TimestampMixin, Base):
    """One row per person brought in: the flat, one-level list.

    No `activated_at` column: "attivo" is derived from contracts at read time.
    A stored flag would need hooks on every path that activates, renews or
    cancels a contract, and any missed path would corrupt the count.
    """

    __tablename__ = "sn_friend_invites"
    __table_args__ = (
        # A customer can be brought in by one person only.
        UniqueConstraint("referred_customer_id", name="uq_sn_friend_invites_referred_customer_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    referrer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    referred_customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_clients.id"))
    #: The code as used, kept for support.
    code_used: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))


class FriendReferralRewardClaim(UUIDPKMixin, TimestampMixin, Base):
    """Request for the gift earned at a milestone (5, 10, 15 ... activated
    referrals). Not an automatic wallet credit: an admin decides the gift
    (SosnetCash, a product, a voucher) case by case.

    UNIQUE (referrer_user_id, milestone) ensures each milestone is claimed at
    most once, whatever happens to the count later.
    """

    __tablename__ = "sn_friend_invite_rewards"
    __table_args__ = (
        UniqueConstraint("referrer_user_id", "milestone", name="uq_sn_friend_invite_rewards_user_milestone"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    referrer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True)
    #: Activated-referral count this gift is for (5, 10, 15 ...).
    milestone: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="REQUESTED", index=True)
    handled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), nullable=True
    )
    handled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
