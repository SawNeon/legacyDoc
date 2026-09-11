"""Per-IP throttling wired into the ASGI stack.

Three tiers, because the endpoints are not equally expensive to abuse. Signing
in is a brute force target, creating a job spends money on an LLM provider, and
reading a job status is polled every couple of seconds by the editor extension.
One number for all three would be either useless or unusable.
"""

from __future__ import annotations

import logging

from legacydoc_core.ratelimit import RateLimitDecision, RateLimitRule, SlidingWindowRateLimiter
from legacydoc_core.settings import Settings
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

AUTH_RULE = RateLimitRule(max_requests=20, window_seconds=300, name="auth")
"""Sign in, sign up and password reset.

Deliberately not the tightest number available. Credential guessing is already
stopped by the account lockout after five failures, so squeezing this further
buys nothing and starts hurting the case that actually happens: a classroom or
an office where everyone shares one public address. Password reset lives in
this tier too, because it sends an email and an open endpoint would turn the
service into a spam relay aimed at an address the attacker picks.
"""

JOB_RULE = RateLimitRule(max_requests=30, window_seconds=300, name="jobs")
"""Job creation, the only path that reaches a paid provider.

The plan quota and the spend ceiling already bound the total, but they are
counted per account. This bounds the burst from a single origin before any
account is even resolved.
"""

READ_RULE = RateLimitRule(max_requests=240, window_seconds=60, name="read")
"""Everything else. Four requests a second sustained covers job polling."""

AUTH_PATHS = frozenset(
    {
        "/v1/auth/login",
        "/v1/auth/register",
        "/v1/auth/password-reset/request",
        "/v1/auth/password-reset/confirm",
    }
)

JOB_CREATION_PATHS = frozenset({"/v1/jobs", "/v1/jobs/upload"})

EXEMPT_PATHS = frozenset({"/health"})


def rule_for(method: str, path: str) -> RateLimitRule | None:
    """Which allowance applies, or None when the route is exempt."""
    if path in EXEMPT_PATHS or method == "OPTIONS":
        return None

    if path in AUTH_PATHS:
        return AUTH_RULE

    if method == "POST" and path in JOB_CREATION_PATHS:
        return JOB_RULE

    return READ_RULE


class RateLimitMiddleware:
    """Rejects before the request reaches routing, authentication or the database.

    Sits under the nginx limit rather than replacing it. The edge limit is a
    flood shield with a high threshold and the cheapest possible rejection;
    this one is the policy, set lower, and it answers with a Retry-After the
    client can actually obey.

    Written against the raw ASGI interface rather than BaseHTTPMiddleware so a
    rejected request never allocates a request object or a task group. The
    point of the limiter is to be cheaper than what it protects.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.limiter = SlidingWindowRateLimiter()
        self.trust_proxy_headers = settings.trust_proxy_headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rule = rule_for(scope["method"], _route_path(scope))

        if rule is None:
            await self.app(scope, receive, send)
            return

        client = self._client_address(scope)
        decision = self.limiter.check(f"{rule.name}:{client}", rule)

        if not decision.allowed:
            logger.warning("Rate limit %s atingido por %s.", rule.name, client)
            await _reject(decision, rule, scope, receive, send)
            return

        await self.app(scope, receive, _with_limit_headers(send, decision, rule))

    def _client_address(self, scope: Scope) -> str:
        """The peer address, taken from the proxy header only when trusted.

        Behind nginx every request arrives from the proxy, so without this the
        whole internet shares one bucket. The header is only believed when the
        deployment declares it sits behind a proxy, because a client can send
        any value it likes and would otherwise get a fresh allowance per
        forged address.
        """
        if self.trust_proxy_headers:
            forwarded = _header(scope, b"x-forwarded-for")

            if forwarded:
                # The proxy appends the address it saw to whatever the client
                # sent, so the trustworthy entry is the last one.
                return forwarded.rsplit(",", 1)[-1].strip()

        peer = scope.get("client")

        return peer[0] if peer else "unknown"


def _route_path(scope: Scope) -> str:
    """Path without the mount prefix, so matching works under a root_path."""
    path = scope["path"]
    root_path = scope.get("root_path") or ""

    if root_path and path.startswith(root_path):
        path = path[len(root_path) :] or "/"

    return path.rstrip("/") or "/"


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", ()):
        if key == name:
            return value.decode("latin-1")

    return ""


def _limit_headers(decision: RateLimitDecision, rule: RateLimitRule) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(rule.max_requests),
        "X-RateLimit-Remaining": str(decision.remaining),
        "X-RateLimit-Window": str(int(rule.window_seconds)),
    }


def _with_limit_headers(send: Send, decision: RateLimitDecision, rule: RateLimitRule) -> Send:
    """Advertise the remaining allowance so clients can pace themselves."""
    extra = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in _limit_headers(decision, rule).items()
    ]

    async def send_with_headers(message: Message) -> None:
        if message["type"] == "http.response.start":
            message = dict(message)
            message["headers"] = list(message.get("headers", [])) + extra

        await send(message)

    return send_with_headers


async def _reject(
    decision: RateLimitDecision,
    rule: RateLimitRule,
    scope: Scope,
    receive: Receive,
    send: Send,
) -> None:
    """Answer 429 in the same envelope every other error uses."""
    headers = _limit_headers(decision, rule)
    headers["Retry-After"] = str(decision.retry_after_seconds)

    response = JSONResponse(
        status_code=429,
        content={
            "error": "rate_limited",
            "message": (
                "Muitas requisicoes em pouco tempo. "
                f"Tente novamente em {decision.retry_after_seconds} segundo(s)."
            ),
            "details": {
                "scope": rule.name,
                "limit": rule.max_requests,
                "window_seconds": int(rule.window_seconds),
            },
        },
        headers=headers,
    )

    await response(scope, receive, send)
