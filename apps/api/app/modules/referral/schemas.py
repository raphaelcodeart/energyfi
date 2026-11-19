import uuid

from pydantic import BaseModel, ConfigDict


class PromoterCodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    personal_link: str
    status: str
    # Set only when resolving someone else's link, so the registration page
    # can show "Invitato da ..."; None on GET /referral/mine.
    promoter_display_name: str | None = None
