import uuid

from pydantic import BaseModel, Field


class ShopCategoryRead(BaseModel):
    id: uuid.UUID
    shop: str
    name: str
    position: int
    active: bool
    #: Products in this category, shown next to each chip in the admin.
    product_count: int = 0


class ShopCategoryCreate(BaseModel):
    shop: str
    name: str = Field(min_length=1, max_length=120)
    position: int = Field(default=0, ge=0, le=9999)


class ShopCategoryUpdate(BaseModel):
    """Partial update: only the fields sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    position: int | None = Field(default=None, ge=0, le=9999)
    active: bool | None = None


class ShopCategoryAssignmentUpdate(BaseModel):
    """Full replacement of one product's categories in one shop; an empty
    list removes them all."""

    shop: str
    product_id: uuid.UUID
    category_ids: list[uuid.UUID] = []


class ShopCategoryAssignmentRead(BaseModel):
    shop: str
    product_id: uuid.UUID
    category_ids: list[uuid.UUID]
