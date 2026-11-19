"""Per-IP fixed-window rate limiting in Redis for abuse-prone public
endpoints (login, register, password reset).

Fails open when Redis is unreachable: a limiter outage must not take down
login or registration."""

import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from app.foundation.config import get_settings

settings = get_settings()
_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _client_ip(request: Request) -> str:
    # nginx overwrites X-Real-IP on every request and the dashboard passes it
    # on, so it names the visitor rather than the dashboard server. The
    # leftmost X-Forwarded-For entry is client-controlled, so it is not used.
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def rate_limit(key_prefix: str, *, max_requests: int, window_seconds: int):
    """Dependency factory: `Depends(rate_limit("login", max_requests=10,
    window_seconds=60))`. Counts per (key_prefix, client IP); per-account
    lockout (User.locked_until) is a separate defense."""

    async def _checker(request: Request) -> None:
        client = _get_redis()
        redis_key = f"ratelimit:{key_prefix}:{_client_ip(request)}"
        try:
            count = await client.incr(redis_key)
            if count == 1:
                await client.expire(redis_key, window_seconds)
        except redis.RedisError:
            return  # fail open -- see module docstring
        if count > max_requests:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Troppi tentativi. Riprova tra qualche minuto.",
            )

    return _checker
