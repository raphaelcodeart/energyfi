"""Shopify app installation (authorization code grant).

Shopify opens our App URL with `?shop=...&hmac=...`; the app counts as
installed only after the merchant passes /admin/oauth/authorize and we
exchange the returned code. Before that, the client credentials grant fails
with "The application is not installed on this shop".

- `install_redirect()` verifies Shopify's hmac and redirects to consent.
- `complete_install()` verifies the hmac and our signed `state`, exchanges
  the code for an offline token, stores it and tests the connection.

`state` is stateless: "<timestamp>.<hmac(client_secret, shop|timestamp)>",
valid for STATE_MAX_AGE seconds. See
https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/authorization-code-grant
"""

import hashlib
import hmac
import time
import urllib.parse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.config import get_settings
from app.modules.shopify_dropshipping import client as shopify
from app.modules.shopify_dropshipping.models import ShopifySettings

SCOPES = "read_products,read_inventory,read_orders,write_orders,write_draft_orders,read_fulfillments"
STATE_MAX_AGE = 900
CALLBACK_PATH = "/api/shopify/oauth/callback"


class ShopifyOAuthError(Exception):
    pass


def callback_url() -> str:
    return get_settings().public_app_base_url.rstrip("/") + CALLBACK_PATH


def verify_hmac(params: dict[str, str], secret: str) -> bool:
    received = params.get("hmac") or ""
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k not in ("hmac", "signature"))
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return bool(received) and hmac.compare_digest(expected, received)


def _sign_state(secret: str, shop: str, ts: int) -> str:
    return f"{ts}." + hmac.new(secret.encode(), f"{shop}|{ts}".encode(), hashlib.sha256).hexdigest()


def _state_ok(secret: str, shop: str, state: str) -> bool:
    try:
        ts = int(state.split(".", 1)[0])
    except ValueError:
        return False
    if abs(time.time() - ts) > STATE_MAX_AGE:
        return False
    return hmac.compare_digest(_sign_state(secret, shop, ts), state)


async def _settings_for_shop(db: AsyncSession, shop: str | None) -> ShopifySettings:
    domain = shopify.normalize_domain(shop)
    if not domain or not domain.endswith(".myshopify.com"):
        raise ShopifyOAuthError("Negozio non valido.")
    row = (
        await db.execute(select(ShopifySettings).where(ShopifySettings.shop_domain == domain))
    ).scalar_one_or_none()
    if row is None or not (row.client_id and row.client_secret):
        raise ShopifyOAuthError(
            f"Il negozio {domain} non è configurato: inserisci dominio, Client ID e secret in Shop Shopify → Impostazioni."
        )
    return row


async def install_redirect(db: AsyncSession, params: dict[str, str]) -> str:
    row = await _settings_for_shop(db, params.get("shop"))
    if not verify_hmac(params, row.client_secret):
        raise ShopifyOAuthError("Firma Shopify non valida: controlla che il Client secret salvato sia quello dell'app.")
    query = urllib.parse.urlencode({
        "client_id": row.client_id,
        "scope": SCOPES,
        "redirect_uri": callback_url(),
        "state": _sign_state(row.client_secret, row.shop_domain, int(time.time())),
    })
    return f"https://{row.shop_domain}/admin/oauth/authorize?{query}"


async def _raw_code_exchange(url: str, payload: dict) -> httpx.Response:
    async with httpx.AsyncClient(timeout=shopify.TIMEOUT_SECONDS) as http:
        return await http.post(url, json=payload, headers={"Accept": "application/json"})


async def complete_install(db: AsyncSession, params: dict[str, str]) -> ShopifySettings:
    row = await _settings_for_shop(db, params.get("shop"))
    if not verify_hmac(params, row.client_secret):
        raise ShopifyOAuthError("Firma Shopify non valida.")
    if not _state_ok(row.client_secret, row.shop_domain, params.get("state") or ""):
        raise ShopifyOAuthError("Richiesta scaduta o non valida: ripeti l'installazione da Shopify.")
    code = params.get("code")
    if not code:
        raise ShopifyOAuthError("Shopify non ha inviato il codice di autorizzazione.")
    try:
        response = await _raw_code_exchange(
            f"https://{row.shop_domain}/admin/oauth/access_token",
            {"client_id": row.client_id, "client_secret": row.client_secret, "code": code},
        )
    except httpx.HTTPError as exc:
        raise ShopifyOAuthError(f"Shopify non risponde ({type(exc).__name__}). Riprova.") from exc
    body = response.json() if response.status_code == 200 else {}
    token = body.get("access_token")
    if not token:
        raise ShopifyOAuthError(f"Shopify non ha rilasciato il token (HTTP {response.status_code}).")
    # Offline tokens never expire; client.py falls back to the client
    # credentials grant only on a 401.
    row.access_token = token[:255]
    row.token_expires_at = None
    await db.commit()
    return row
