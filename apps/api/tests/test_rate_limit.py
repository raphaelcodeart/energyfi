"""Rate limits must count each visitor separately, even though every request
reaches the API through the dashboard server."""

from starlette.requests import Request

from app.foundation.rate_limit import _client_ip


def _request(headers: dict[str, str], host: str = "172.18.0.6") -> Request:
    return Request({
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (host, 12345),
    })


def test_visitor_ip_comes_from_x_real_ip():
    assert _client_ip(_request({"X-Real-IP": "93.44.1.7"})) == "93.44.1.7"


def test_forged_forwarded_for_is_ignored():
    request = _request({"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "93.44.1.7"})
    assert _client_ip(request) == "93.44.1.7"


def test_without_proxy_headers_the_peer_address_is_used():
    assert _client_ip(_request({})) == "172.18.0.6"
