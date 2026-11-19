"""Cart request bodies: a variant and a quantity, never a price or total.

Prices are recomputed server-side on every read, so the client sends none.
"""

import uuid

from pydantic import BaseModel, Field

from app.modules.carts.models import MAX_ITEM_QUANTITY


class CartItemAddRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=MAX_ITEM_QUANTITY)


class CartItemQuantityUpdate(BaseModel):
    #: Zero removes the line rather than being rejected.
    quantity: int = Field(ge=0, le=MAX_ITEM_QUANTITY)
