"""HTTP client for the Mamify API ("Mamify - Documentazione API", 1/11/2026).

Every call is `POST <base>/<path>` with a JSON body and the web app's key in
`X-Fw360-Key`. Success is `{"status": 1, "data": ...}`, failure
`{"status": 0, "error": code, "message": text}`, and an unknown path answers
`["status", "wrong_endpoint"]`.

**Read only.** Mamify is the source of people, tree, orders and wallets, and
SOS Affiliate must never change it: no creation, update or deletion, ever.
The client therefore refuses, before any network traffic, every path that is
not in `READ_ONLY_PATHS`. Adding a path there is a deliberate decision that
the path only reads; a test pins the list.

Rate limit: each key has its own budget (60 calls a minute when this was
written). The client reads `X-RateLimit-Remaining`/`-Reset` on every answer
and waits for the window to reset when the budget is about to run out, and
waits out a 429 (Retry-After) a few times before giving up.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(60.0, connect=10.0)
#: Longest wait for one rate-limit window, and how many 429 in a row are waited out.
MAX_RETRY_AFTER_SECONDS = 65
MAX_RATE_RETRIES = 4
#: Calls kept in reserve in each window, for the admin page and logins.
RATE_RESERVE = 3

#: Every path SOS Affiliate may call. All of them only read: the service
#: API (§11, "Sola lettura") and the login, which checks a person's
#: password and changes nothing on Mamify's data.
READ_ONLY_PATHS = frozenset({
    "plugins/mamify/rag/customer/find",
    "plugins/mamify/rag/customer/network",
    "plugins/mamify/rag/customer/orders",
    "plugins/mamify/rag/customer/wallets",
    "plugins/mamify/rag/customer/transactions",
    "plugins/mamify/rag/apps/list",
    "plugins/mamify/rag/products/search",
    "plugins/mamify/auth/login",
})

#: Italian text for the documented error codes; anything else shows Mamify's
#: own message.
ERROR_MESSAGES = {
    "wrong_api_key": "La chiave API di Mamify non è valida.",
    "insufficient_permissions": "La chiave API non ha il permesso per questa chiamata: va spuntata nel CRM di Mamify.",
    "login_required": "Mamify chiede l'accesso di un cliente per questa chiamata.",
    "customer_token_expired": "L'accesso a Mamify è scaduto.",
    "rate_limited": "Troppe chiamate a Mamify: riprova tra poco.",
    "wrong_credentials": "Email o password di Mamify non corretti.",
    "wrong_params": "Mamify ha rifiutato i parametri della chiamata.",
    "wrong_endpoint": "Mamify non riconosce questa chiamata.",
    "customer_not_found": "Cliente non trovato su Mamify.",
    "customer_ambiguous": "Su Mamify ci sono più clienti con questi dati.",
    "customer_identifier_required": "Manca il cliente Mamify a cui si riferisce la chiamata.",
    "write_blocked": "Chiamata bloccata: SOS Affiliate usa Mamify solo in lettura.",
}


class MamifyApiError(Exception):
    """A call Mamify refused or that did not reach it. `code` is Mamify's
    error code, or "network"/"http_<n>" when there was no Mamify answer."""

    def __init__(self, code: str, message: str | None = None, *, uncertain: bool = False):
        self.code = code
        #: True when the answer is unknown (timeout, dropped connection).
        self.uncertain = uncertain
        super().__init__(ERROR_MESSAGES.get(code) or message or f"Errore di Mamify ({code}).")


def assert_read_only(path: str) -> str:
    clean = path.strip().strip("/")
    if clean not in READ_ONLY_PATHS:
        logger.error("Blocked Mamify call to %s: not a read-only path", clean)
        raise MamifyApiError("write_blocked", f"Chiamata a «{clean}» bloccata: SOS Affiliate usa Mamify solo in lettura.")
    return clean


class _Window:
    """What the last answer said about the key's budget (per process)."""

    remaining: int | None = None
    reset_at: float | None = None


class MamifyClient:
    def __init__(self, base_url: str, api_key: str, *, functionality: str | None = None, lang: str = "it",
                 transport: httpx.AsyncBaseTransport | None = None, sleep=asyncio.sleep):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.functionality = functionality
        self.lang = lang
        self._transport = transport
        self._sleep = sleep
        #: Calls actually sent by this client, for the sync report.
        self.calls = 0

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Fw360-Key": self.api_key,
            "X-Fw360-Lang": self.lang,
            "X-Fw360-Currency": "EUR",
            # Service calls must not carry a customer token (§11).
            "X-Fw360-Customertoken": "",
        }
        if self.functionality:
            headers["X-Fw360-App"] = self.functionality
        return headers

    async def call(self, path: str, data: dict[str, Any] | None = None) -> Any:
        """Returns the `data` of a successful answer, raises MamifyApiError otherwise."""
        clean = assert_read_only(path)
        body = await self._post(clean, data or {})
        return self._unwrap(body)

    async def _respect_window(self) -> None:
        remaining, reset_at = _Window.remaining, _Window.reset_at
        if remaining is None or reset_at is None or remaining > RATE_RESERVE:
            return
        wait = reset_at - time.time()
        if 0 < wait <= MAX_RETRY_AFTER_SECONDS:
            await self._sleep(wait + 0.5)
        _Window.remaining = None

    @staticmethod
    def _remember_window(response: httpx.Response) -> None:
        try:
            remaining = response.headers.get("X-RateLimit-Remaining")
            reset = response.headers.get("X-RateLimit-Reset")
            _Window.remaining = int(remaining) if remaining is not None else None
            _Window.reset_at = float(reset) if reset is not None else None
        except ValueError:
            _Window.remaining = _Window.reset_at = None

    async def _post(self, path: str, data: dict) -> Any:
        url = f"{self.base_url}/{path}"
        for attempt in range(MAX_RATE_RETRIES + 1):
            await self._respect_window()
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT, transport=self._transport) as http:
                    response = await http.post(url, json=data, headers=self._headers())
            except httpx.TimeoutException as exc:
                raise MamifyApiError("network", "Mamify non ha risposto in tempo.", uncertain=True) from exc
            except httpx.HTTPError as exc:
                raise MamifyApiError("network", "Mamify non è raggiungibile.",
                                     uncertain=not isinstance(exc, httpx.ConnectError)) from exc
            self.calls += 1
            self._remember_window(response)
            if response.status_code == 429 and attempt < MAX_RATE_RETRIES:
                try:
                    wait = int(response.headers.get("Retry-After") or 10)
                except ValueError:
                    wait = 10
                await self._sleep(min(max(wait, 1), MAX_RETRY_AFTER_SECONDS))
                continue
            break
        try:
            body = response.json()
        except ValueError as exc:
            raise MamifyApiError(f"http_{response.status_code}", f"Risposta non leggibile da Mamify (HTTP {response.status_code}).",
                                 uncertain=response.status_code >= 500) from exc
        if response.status_code >= 400 and not isinstance(body, dict | list):
            raise MamifyApiError(f"http_{response.status_code}")
        return body

    @staticmethod
    def _error(body: Any) -> MamifyApiError:
        if isinstance(body, list) and "wrong_endpoint" in body:
            return MamifyApiError("wrong_endpoint")
        if isinstance(body, dict):
            return MamifyApiError(str(body.get("error") or "unknown"), body.get("message"))
        return MamifyApiError("unknown", "Risposta inattesa da Mamify.")

    @classmethod
    def _unwrap(cls, body: Any) -> Any:
        if isinstance(body, dict) and body.get("status") in (1, True, "1"):
            return body.get("data", body)
        raise cls._error(body)
