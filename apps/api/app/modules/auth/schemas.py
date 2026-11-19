from pydantic import BaseModel, EmailStr, field_validator

from app.foundation.normalization import normalize_email, normalize_person_name


def _strip(v: object) -> object:
    """Strip whitespace accidentally pasted around a password so it does not
    cause a spurious mismatch. Emails use normalize_email instead."""
    return v.strip() if isinstance(v, str) else v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: object) -> object:
        return normalize_email(v) if isinstance(v, str) else v

    @field_validator("password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return _strip(v)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeRead(BaseModel):
    roles: list[str]
    # Live account-gate flags for the dashboard's blocking popups
    # (docs/business-rules.md#account-gates). Never embedded in the access token.
    email_verified: bool
    profile_complete: bool
    privacy_accepted: bool


class RegisterRequest(BaseModel):
    organization_id: str
    # Registration is invite-only: every customer must arrive through a
    # referral link (docs/business-rules.md).
    referral_code: str
    email: EmailStr
    password: str
    kind: str  # PRIVATE / SOLE_PROPRIETOR / COMPANY / CONDOMINIUM
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    phone: str | None = None
    # Server-side enforcement of the mandatory privacy-policy checkbox.
    accept_privacy: bool = False

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: object) -> object:
        return normalize_email(v) if isinstance(v, str) else v

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_name_fields(cls, v: object) -> object:
        return normalize_person_name(v) if isinstance(v, str) else v

    @field_validator("password", "referral_code", "company_name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return _strip(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v

    @field_validator("accept_privacy")
    @classmethod
    def validate_accept_privacy(cls, v: bool) -> bool:
        if not v:
            raise ValueError("privacy policy must be accepted to register")
        return v


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    pass


class ForgotPasswordRequest(BaseModel):
    organization_id: str
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, v: object) -> object:
        return normalize_email(v) if isinstance(v, str) else v


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: object) -> object:
        return _strip(v)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v
