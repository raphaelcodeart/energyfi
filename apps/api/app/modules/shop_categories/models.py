"""Shop categories: the filter chips shown above each Shop grid, kept as a
layer on top of the products rather than a column inside them.

The Shop sells from the three sections of the internal catalog
(`catalog.products`, split by `Product.category`) and from the imported-product
shops (AliExpress, CJ, Shopify, Sosnet Market; the hand-made
`imported_products` appear inside the AliExpress tab). Each keeps its own
product table and knows nothing about this module: nothing here writes to
those tables, and dropping these two tables removes the feature entirely.

This isolation is why categories have their own table instead of a
`category_id` column on every product table: a new shop gains categories by
adding a string to SHOPS, without a migration per shop.

`Product.category` (INTERNAL / PARTNER / DROPSHIPPING) is unrelated: it
decides WHICH shop a catalog product belongs to, while a ShopCategory decides
where it sits INSIDE that shop.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.foundation.db import Base, TimestampMixin, UUIDPKMixin

#: Grids a category can belong to. The catalog entries equal the lower-cased
#: `Product.category` (see shop_for_catalog_category). `imported_products`
#: rows are shown in the AliExpress tab and categorised under "aliexpress".
SHOPS = ("internal", "partner", "dropshipping", "aliexpress", "cj", "shopify", "sosnet_market")

#: The subset backed by `catalog.products`.
CATALOG_SHOPS = ("internal", "partner", "dropshipping")


def shop_for_catalog_category(category: str | None) -> str:
    """Shop of a `catalog.products` row: its lower-cased `Product.category`,
    so the two vocabularies cannot drift (see PRODUCT_CATEGORIES in
    catalog/schemas.py)."""
    return (category or "INTERNAL").lower()


class ShopCategory(UUIDPKMixin, TimestampMixin, Base):
    """One filter chip in one shop.

    Names are unique per (organization, shop), case-insensitively via the
    index on lower(name). The service checks this first so the user gets an
    Italian message rather than an integrity error.
    """

    __tablename__ = "sn_catalog_sections"
    __table_args__ = (
        Index(
            "uq_sn_catalog_sections_organization_id_shop_name",
            "organization_id",
            "shop",
            text("lower(name)"),
            unique=True,
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_tenants.id"), index=True
    )
    #: One of SHOPS.
    shop: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(120))
    #: Display order; ties broken by name.
    position: Mapped[int] = mapped_column(Integer, default=0)
    #: Inactive categories keep their products but are hidden from customers.
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ShopCategoryProduct(UUIDPKMixin, TimestampMixin, Base):
    """Many-to-many link between products and categories.

    `product_id` deliberately has **no foreign key**: it points into one of
    several product tables, distinguished by `shop`. The database cannot
    enforce existence, so the service always resolves the id against its
    shop; a deleted product just leaves an orphan row that no list reads.
    """

    __tablename__ = "sn_catalog_section_items"
    __table_args__ = (
        UniqueConstraint("category_id", "product_id", name="uq_sn_catalog_section_items_category_id"),
        #: Serves "categories of these ids in this shop", one query per page.
        Index(
            "ix_sn_catalog_section_items_organization_id_shop_product_id",
            "organization_id",
            "shop",
            "product_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sn_tenants.id"))
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sn_catalog_sections.id", ondelete="CASCADE"), index=True
    )
    #: Denormalized from the category: avoids a join, and keeps a stale
    #: assignment of a product that changed shop out of the wrong grid.
    shop: Mapped[str] = mapped_column(String(16))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
