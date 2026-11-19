from pydantic import BaseModel, Field


class GoogleDriveStatusRead(BaseModel):
    """Connection status; never exposes a secret.

    Neither `client_secret` nor the refresh token is returned in any form:
    only whether the secret is set and whether the connection is active."""

    #: Client ID and secret are set, so authorization can start.
    configured: bool
    #: A Google account has been authorized.
    connected: bool
    account_email: str | None = None
    connected_at: str | None = None
    #: If set, contract folders are created here instead of the Drive root
    #: of the authorizing account.
    parent_folder_id: str | None = None
    #: Paste verbatim into the OAuth client's "Authorized redirect URIs" in
    #: the Google Cloud console.
    redirect_uri: str
    #: Not secret (it travels in the consent URL); showing it is the only way
    #: to spot a mis-pasted value.
    client_id: str | None = None
    client_secret_configured: bool = False


class GoogleDriveCredentialsUpdate(BaseModel):
    client_id: str | None = Field(default=None, max_length=255)
    client_secret: str | None = Field(default=None, max_length=255)
    parent_folder_id: str | None = Field(default=None, max_length=255)


class GoogleDriveAuthorizeUrlRead(BaseModel):
    url: str


class GoogleDriveCallbackRequest(BaseModel):
    code: str
    state: str


class DriveUploadResultRead(BaseModel):
    folder_name: str
    folder_url: str
    #: Files newly created.
    uploaded: int
    #: Existing files overwritten; re-running the export never duplicates.
    replaced: int
