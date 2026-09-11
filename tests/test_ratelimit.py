"""Rate limiting: the window arithmetic and the HTTP behaviour it produces."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from legacydoc_api.ratelimit import AUTH_RULE, JOB_RULE, READ_RULE, rule_for
from legacydoc_core.ratelimit import RateLimitRule, SlidingWindowRateLimiter

RULE = RateLimitRule(max_requests=3, window_seconds=60, name="teste")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def limiter(clock: FakeClock) -> SlidingWindowRateLimiter:
    return SlidingWindowRateLimiter(clock=clock)


def _spend_allowance(limiter: SlidingWindowRateLimiter, key: str = "ip") -> None:
    for _ in range(RULE.max_requests):
        limiter.check(key, RULE)


# --------------------------------------------------------------- contagem


def test_requests_within_the_allowance_pass(limiter):
    assert [limiter.check("ip", RULE).allowed for _ in range(3)] == [True, True, True]


def test_request_beyond_the_allowance_is_denied(limiter):
    _spend_allowance(limiter)

    assert limiter.check("ip", RULE).allowed is False


def test_keys_do_not_share_an_allowance(limiter):
    _spend_allowance(limiter, "ip-a")

    assert limiter.check("ip-b", RULE).allowed is True


def test_remaining_counts_down_to_zero(limiter):
    assert [limiter.check("ip", RULE).remaining for _ in range(3)] == [2, 1, 0]


def test_allowance_returns_after_the_window_fully_decays(limiter, clock):
    _spend_allowance(limiter)
    clock.advance(120)

    assert limiter.check("ip", RULE).allowed is True


def test_boundary_burst_is_not_double_counted(limiter, clock):
    """A plain fixed window would allow the whole allowance twice here.

    Spending everything at the end of one window and again at the start of the
    next is the classic way to double the intended rate. The previous window
    still weighs almost full one second in, so the burst is refused.
    """
    clock.advance(59)
    _spend_allowance(limiter)
    clock.advance(2)

    assert limiter.check("ip", RULE).allowed is False


# ----------------------------------------------------------- retry-after


def test_retry_after_is_always_actionable(limiter):
    _spend_allowance(limiter)

    assert limiter.check("ip", RULE).retry_after_seconds >= 1


def test_waiting_the_advertised_time_actually_works(limiter, clock):
    """A Retry-After the client obeys and still gets refused is a broken header."""
    _spend_allowance(limiter)

    denied = limiter.check("ip", RULE)
    clock.advance(denied.retry_after_seconds)

    assert limiter.check("ip", RULE).allowed is True


# --------------------------------------------------------------- memoria


def test_key_space_is_bounded(clock):
    """The key is the caller's address, so growth has to have a ceiling."""
    limiter = SlidingWindowRateLimiter(max_tracked_keys=100, clock=clock)

    for index in range(5_000):
        limiter.check(f"ip-{index}", RULE)

    assert len(limiter._states) <= 100


def test_the_active_key_survives_eviction(clock):
    """Eviction drops the least recently seen, not whoever is hammering."""
    limiter = SlidingWindowRateLimiter(max_tracked_keys=10, clock=clock)

    for index in range(100):
        limiter.check("atacante", RULE)
        limiter.check(f"ip-{index}", RULE)

    assert limiter.check("atacante", RULE).allowed is False


def test_invalid_rules_are_rejected_at_construction():
    with pytest.raises(ValueError):
        RateLimitRule(max_requests=0, window_seconds=60)

    with pytest.raises(ValueError):
        RateLimitRule(max_requests=5, window_seconds=0)


# ------------------------------------------------------------------ rotas


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/v1/auth/login", AUTH_RULE),
        ("POST", "/v1/auth/register", AUTH_RULE),
        ("POST", "/v1/auth/password-reset/request", AUTH_RULE),
        ("POST", "/v1/jobs", JOB_RULE),
        ("POST", "/v1/jobs/upload", JOB_RULE),
        ("GET", "/v1/jobs", READ_RULE),
        ("GET", "/v1/documents", READ_RULE),
        ("GET", "/health", None),
        ("OPTIONS", "/v1/auth/login", None),
    ],
)
def test_each_route_gets_the_intended_tier(method, path, expected):
    assert rule_for(method, path) is expected


def test_reading_is_more_generous_than_signing_in():
    """The editor extension polls job status; login is a brute force target."""
    read_rate = READ_RULE.max_requests / READ_RULE.window_seconds
    auth_rate = AUTH_RULE.max_requests / AUTH_RULE.window_seconds

    assert read_rate > auth_rate


# ------------------------------------------------------------------- http


@pytest.fixture
def throttled_settings(settings):
    return settings.model_copy(update={"rate_limit_enabled": True})


@pytest.fixture
async def throttled_client(session_factory, throttled_settings):
    from legacydoc_api.main import create_app

    app = create_app(throttled_settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
        yield http


async def _attempt_login(client: AsyncClient):
    """An unknown account, so the cost is a lookup and not a password hash."""
    return await client.post(
        "/v1/auth/login",
        json={
            "email": f"user-{uuid.uuid4().hex[:8]}@exemplo.com",
            "password": "senha-bem-longa-123",
        },
    )


async def _exhaust_auth_tier(client: AsyncClient):
    response = None

    for _ in range(AUTH_RULE.max_requests + 1):
        response = await _attempt_login(client)

    return response


async def test_repeated_sign_in_attempts_are_throttled(throttled_client):
    statuses = []

    for _ in range(AUTH_RULE.max_requests + 1):
        statuses.append((await _attempt_login(throttled_client)).status_code)

    assert statuses.count(401) == AUTH_RULE.max_requests
    assert statuses[-1] == 429


async def test_signing_up_shares_the_sign_in_allowance(throttled_client):
    """One tier covers the whole credential surface.

    Separate allowances per endpoint would let an attacker switch from login to
    sign up and get a fresh budget for the same abuse.
    """
    await _exhaust_auth_tier(throttled_client)

    response = await throttled_client.post(
        "/v1/auth/register",
        json={"email": "novo@exemplo.com", "password": "senha-bem-longa-123"},
    )

    assert response.status_code == 429


async def test_the_rejection_keeps_the_shared_error_shape(throttled_client):
    response = await _exhaust_auth_tier(throttled_client)
    body = response.json()

    assert response.status_code == 429
    assert body["error"] == "rate_limited"
    assert int(response.headers["Retry-After"]) >= 1
    assert response.headers["X-RateLimit-Limit"] == str(AUTH_RULE.max_requests)


async def test_the_rejection_still_carries_cors_headers(throttled_client):
    """Without them the browser reports a network error instead of the 429.

    This is what pins the middleware order: the limiter has to be registered
    before CORS so that CORS ends up wrapping it.
    """
    origin = "http://localhost:5173"

    for _ in range(AUTH_RULE.max_requests + 1):
        response = await throttled_client.post(
            "/v1/auth/login",
            json={"email": "quem@exemplo.com", "password": "senha-bem-longa-123"},
            headers={"Origin": origin},
        )

    assert response.status_code == 429
    assert response.headers["access-control-allow-origin"] == origin


async def test_successful_responses_advertise_the_remaining_allowance(throttled_client):
    response = await throttled_client.get("/v1/meta/plans")

    assert response.status_code == 200
    assert int(response.headers["X-RateLimit-Remaining"]) == READ_RULE.max_requests - 1


async def test_health_is_never_throttled(throttled_client):
    """Monitoring must not be able to lock itself out."""
    response = None

    for _ in range(READ_RULE.max_requests + 5):
        response = await throttled_client.get("/health")

    assert response.status_code == 200


async def test_exhausting_the_auth_tier_leaves_reads_working(throttled_client):
    """Tiers are independent: a login flood must not take the API down."""
    await _exhaust_auth_tier(throttled_client)

    assert (await throttled_client.get("/v1/meta/plans")).status_code == 200


# ------------------------------------------------------------------ proxy


def _scope(*, client_host: str, forwarded: str = "") -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": "/v1/jobs",
        "headers": [(b"x-forwarded-for", forwarded.encode())] if forwarded else [],
        "client": (client_host, 5000),
    }


def _middleware(settings, *, trust: bool):
    from legacydoc_api.ratelimit import RateLimitMiddleware

    async def noop_app(scope, receive, send):
        return None

    return RateLimitMiddleware(noop_app, settings.model_copy(update={"trust_proxy_headers": trust}))


def test_forwarded_address_is_ignored_when_proxies_are_not_trusted(settings):
    middleware = _middleware(settings, trust=False)

    address = middleware._client_address(_scope(client_host="10.0.0.1", forwarded="1.2.3.4"))

    assert address == "10.0.0.1"


def test_forwarded_address_is_read_from_the_end_of_the_chain(settings):
    """nginx appends the address it saw, so only the last entry is trustworthy.

    Reading the first entry instead would let any caller forge an address and
    hand itself an unlimited allowance.
    """
    middleware = _middleware(settings, trust=True)

    address = middleware._client_address(
        _scope(client_host="10.0.0.1", forwarded="9.9.9.9, 203.0.113.7")
    )

    assert address == "203.0.113.7"
