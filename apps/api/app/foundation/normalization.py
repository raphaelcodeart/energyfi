import re

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_person_name(v: str | None) -> str | None:
    """Trim, collapse whitespace runs and uppercase, so every spelling of a
    name is stored identically. Used as a mode="before" validator on all
    first/last name fields. None passes through (an omitted field must not
    become "NONE")."""
    if v is None:
        return v
    return _WHITESPACE_RUN.sub(" ", v.strip()).upper()


def normalize_email(v: str | None) -> str | None:
    """Remove all whitespace (a pasted stray space would otherwise fail
    EmailStr) and lowercase, so one inbox cannot map to two accounts that
    differ only by case. None passes through."""
    if v is None:
        return v
    return _WHITESPACE_RUN.sub("", v.strip()).lower()
