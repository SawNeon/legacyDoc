"""Generation depth: what the customer asked for, capped by what they pay for."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from legacydoc_core.models import Job, User
from legacydoc_core.plans import (
    DEPTH_ORDER,
    GenerationDepth,
    PlanTier,
    get_plan,
    resolve_depth,
)
from sqlalchemy import select


def test_each_depth_adds_one_agent_to_the_previous_one():
    """The ladder has to be monotonic, or a deeper pass could analyse less."""
    assert not GenerationDepth.BASIC.runs_improver
    assert not GenerationDepth.BASIC.runs_verifier

    assert GenerationDepth.STANDARD.runs_improver
    assert not GenerationDepth.STANDARD.runs_verifier

    assert GenerationDepth.PRO.runs_improver
    assert GenerationDepth.PRO.runs_verifier


def test_the_order_is_cheapest_first():
    assert [depth.rank for depth in DEPTH_ORDER] == [0, 1, 2]


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        (PlanTier.FREE, [GenerationDepth.BASIC]),
        (PlanTier.PRO, list(DEPTH_ORDER)),
        (PlanTier.TEAM, list(DEPTH_ORDER)),
    ],
)
def test_each_plan_publishes_the_depths_it_can_pick(tier, expected):
    assert get_plan(tier).available_depths == expected


def test_asking_above_the_plan_is_capped_not_refused():
    """A client that always sends the deepest option must keep working."""
    assert resolve_depth(GenerationDepth.PRO, get_plan(PlanTier.FREE)) is GenerationDepth.BASIC


def test_a_paid_plan_can_deliberately_ask_for_less():
    assert resolve_depth(GenerationDepth.BASIC, get_plan(PlanTier.PRO)) is GenerationDepth.BASIC


def test_omitting_the_depth_spends_everything_the_plan_allows():
    assert resolve_depth(None, get_plan(PlanTier.PRO)) is GenerationDepth.PRO


def test_an_unrecognised_value_falls_back_instead_of_crashing():
    """Stored job parameters are re-read long after they were written."""
    assert resolve_depth("turbo", get_plan(PlanTier.PRO)) is GenerationDepth.PRO


async def _register(client: AsyncClient) -> tuple[dict[str, str], str]:
    email = f"d-{uuid.uuid4().hex[:10]}@exemplo.com"

    response = await client.post(
        "/v1/auth/register", json={"email": email, "password": "senha-bem-longa-123"}
    )
    assert response.status_code == 201, response.text

    return {"Authorization": f"Bearer {response.json()['access_token']}"}, email


async def _set_plan(session, email: str, plan: str) -> None:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    user.plan_tier = plan
    await session.commit()


async def _create_snippet_job(client: AsyncClient, headers: dict[str, str], **extra):
    return await client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "job_type": "document_snippet",
            "path": "calc.py",
            "content": "def somar(a, b):\n    return a + b\n",
            **extra,
        },
    )


async def test_a_paid_account_can_choose_the_cheap_pass(client: AsyncClient, session):
    headers, email = await _register(client)
    await _set_plan(session, email, "pro")

    response = await _create_snippet_job(client, headers, depth="basic")

    assert response.status_code == 202
    assert response.json()["depth"] == "basic"


async def test_a_paid_account_gets_the_deepest_pass_by_default(client: AsyncClient, session):
    headers, email = await _register(client)
    await _set_plan(session, email, "pro")

    response = await _create_snippet_job(client, headers)

    assert response.json()["depth"] == "pro"


async def test_a_free_account_is_capped(client: AsyncClient, session):
    headers, _ = await _register(client)

    response = await _create_snippet_job(client, headers, depth="pro")

    assert response.status_code == 202
    assert response.json()["depth"] == "basic"


async def test_an_invalid_depth_is_rejected_at_the_contract(client: AsyncClient):
    headers, _ = await _register(client)

    response = await _create_snippet_job(client, headers, depth="ultra")

    assert response.status_code == 422


async def test_the_stored_job_carries_the_effective_depth(client: AsyncClient, session):
    """The worker reads this, so it has to be the capped value, never the asked one."""
    headers, _ = await _register(client)
    await _create_snippet_job(client, headers, depth="pro")

    job = (await session.execute(select(Job))).scalars().one()

    assert job.params["depth"] == "basic"


async def test_the_plan_endpoint_feeds_the_front_selector(client: AsyncClient):
    """The front builds the selector from this instead of hardcoding the ladder."""
    plans = {plan["tier"]: plan for plan in (await client.get("/v1/meta/plans")).json()}

    assert plans["free"]["available_depths"] == ["basic"]
    assert plans["pro"]["available_depths"] == ["basic", "standard", "pro"]
    assert plans["pro"]["max_depth"] == "pro"


async def test_the_account_endpoint_reports_the_same_ladder(client: AsyncClient, session):
    headers, email = await _register(client)
    await _set_plan(session, email, "pro")

    body = (await client.get("/v1/auth/me", headers=headers)).json()

    assert body["plan"]["available_depths"] == ["basic", "standard", "pro"]


async def test_the_document_response_carries_the_badge_the_front_shows(
    client: AsyncClient, session
):
    """Without this the front cannot label a card without a second request."""
    from legacydoc_core.models import Document

    headers, email = await _register(client)
    await _set_plan(session, email, "pro")

    job_id = (await _create_snippet_job(client, headers, depth="standard")).json()["id"]
    job = await session.get(Job, uuid.UUID(job_id))

    session.add(
        Document(
            job_id=job.id,
            user_id=job.user_id,
            path="src/app.py",
            language="python",
            content_sha256="a" * 64,
            summary="Resumo.",
            symbols=[],
            depth="standard",
        )
    )
    await session.commit()

    listed = (await client.get("/v1/documents", headers=headers)).json()

    assert listed[0]["depth"] == "standard"

    detail = (await client.get(f"/v1/documents/{listed[0]['id']}", headers=headers)).json()

    assert detail["depth"] == "standard"
