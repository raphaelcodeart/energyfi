"""Shop cart.

**One cart per shop.** The Marketplaces carry a delivery address, shipping,
frozen VAT and the bank-transfer discount; the internal catalog (Partner
Products and Sosnet Offers) has none of these but offers instant cashback,
which the Marketplaces forbid (marketplaces/rules.py). Lines with mutually
exclusive rules cannot share an order, so they cannot share a cart. The
customer still sees a single cart split into sections: the top total is the
sum, and each section has its own checkout button.

Each line references its shop's variant through a dedicated nullable column,
with exactly one set (`exactly_one_reference`). This costs one column per
shop but keeps real foreign keys: deleting a variant cascades to the cart
lines that reference it instead of leaving dangling ids.

**Carts hold no prices**, only what and how many. The price is computed
server-side at checkout from current list prices and frozen on the order.
"""

import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

#: Shops with a cart. "catalog" is the internal catalog: Partner Products
#: and Sosnet Offers are two tabs over `catalog.products` (PARTNER and
#: DROPSHIPPING) and share one cart, one order and one payment.
CART_SHOPS = ("aliexpress", "cj", "shopify", "sosnet_market", "catalog")

#: Sanity cap per line, not a stock rule (stock is checked with the supplier
#: at checkout); it stops a bad `quantity` from becoming a huge order.
MAX_ITEM_QUANTITY = 99


class Cart(UUIDPKMixin, TimestampMixin, Base):
    """A customer's open cart for one shop. The UNIQUE (customer, shop)
    constraint makes cart creation idempotent at the database level. After
    checkout the cart is emptied, never deleted, so its id stays stable and
    concurrent requests cannot create two."""

    __tablename__ = "sn_baskets"
    __table_args__ = (
        UniqueConstraint("customer_user_id", "shop", name="uq_sn_baskets_customer_shop"),
        CheckConstraint(
            "shop IN ('aliexpress', 'cj', 'shopify', 'sosnet_market', 'catalog')", name="shop"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    customer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_accounts.id"), index=True
    )
    shop: Mapped[str] = mapped_column(String(16))


class CartItem(UUIDPKMixin, TimestampMixin, Base):
    """A cart line: one variant and a quantity.

    Every reference cascades on delete: when an admin removes a product or
    variant, cart lines pointing to it go too. Orders are unaffected since
    they hold frozen snapshots.
    """

    __tablename__ = "sn_basket_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(f"quantity <= {MAX_ITEM_QUANTITY}", name="quantity_max"),
        # Exclusive arc: a line belongs to exactly one shop.
        CheckConstraint(
            "num_nonnulls(aliexpress_variant_id, cj_variant_id, shopify_variant_id,"
            " sosnet_market_variant_id, product_version_id) = 1",
            name="exactly_one_reference",
        ),
        # One line per variant: re-adding bumps the quantity. Separate
        # constraints because PostgreSQL UNIQUE ignores rows where the
        # column is NULL.
        UniqueConstraint("cart_id", "aliexpress_variant_id", name="uq_sn_basket_lines_aliexpress_variant"),
        UniqueConstraint("cart_id", "cj_variant_id", name="uq_sn_basket_lines_cj_variant"),
        UniqueConstraint("cart_id", "shopify_variant_id", name="uq_sn_basket_lines_shopify_variant"),
        UniqueConstraint("cart_id", "sosnet_market_variant_id", name="uq_sn_basket_lines_sosnet_market_variant"),
        UniqueConstraint("cart_id", "product_version_id", name="uq_sn_basket_lines_product_version"),
    )

    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_baskets.id", ondelete="CASCADE"), index=True
    )
    quantity: Mapped[int] = mapped_column(BigInteger, default=1)

    # --- Exclusive arc: exactly one of these is set ---
    aliexpress_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_aliexpress_item_variants.id", ondelete="CASCADE"), nullable=True
    )
    cj_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_cj_item_variants.id", ondelete="CASCADE"), nullable=True
    )
    shopify_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_shopify_item_variants.id", ondelete="CASCADE"), nullable=True
    )
    sosnet_market_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_market_item_variants.id", ondelete="CASCADE"), nullable=True
    )
    #: The internal catalog has no variants; the product version plays that
    #: role, matching what orders.Order freezes.
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_offer_versions.id", ondelete="CASCADE"), nullable=True
    )
