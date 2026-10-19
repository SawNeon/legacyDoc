"""Pricing rules in the database, credit balance, top-ups and the admin controls over them."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from legacydoc_core.billing import (
    RECOMMENDED_PLANS,
    RECOMMENDED_SETTINGS,
    add_months,
    balance_for,
    ceiling_usd,
    grant_credit,
    load_pricing,
    margin_percent,
    next_month_start,
    settle_overflow,
)
from legacydoc_core.models import (
    AdminAction,
    BillingSetting,
    CreditGrant,
    PlanPricing,
    UsageRecord,
    UsageSettlement,
    User,
)
from sqlalchemy import func, select

JOB = {"job_type": "document_snippet", "path": "a.py", "content": "def f(): pass"}
FREE_CEILING = 5.0 * 0.55 / 6.0
PRO_CEILING = 120.0 * 0.55 / 6.0


async def _register(client: AsyncClient) -> tuple[dict[str, str], str]:
    email = f"b-{uuid.uuid4().hex[:10]}@exemplo.com"

    response = await client.post(
        "/v1/auth/register", json={"email": email, "password": "senha-bem-longa-123"}
    )
    assert response.status_code == 201, response.text

    return {"Authorization": f"Bearer {response.json()['access_token']}"}, email


async def _user(session, email: str) -> User:
    return (await session.execute(select(User).where(User.email == email))).scalar_one()


async def _promote(session, email: str) -> None:
    (await _user(session, email)).is_admin = True
    await session.commit()


async def _admin(client: AsyncClient, session) -> dict[str, str]:
    headers, email = await _register(client)
    await _promote(session, email)

    return headers


async def _set_plan(session, email: str, tier: str) -> None:
    (await _user(session, email)).plan_tier = tier
    await session.commit()


async def _spend(session, user_id, amount: float) -> None:
    session.add(
        UsageRecord(
            user_id=user_id,
            agent="writer",
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=1,
            output_tokens=1,
            cost_usd=amount,
        )
    )
    await session.commit()


async def _usage(client: AsyncClient, headers) -> dict:
    response = await client.get("/v1/usage", headers=headers)
    assert response.status_code == 200, response.text

    return response.json()


async def _create_job(client: AsyncClient, headers):
    return await client.post("/v1/jobs", json=JOB, headers=headers)


async def _patch_plan(client: AsyncClient, headers, tier: str, **fields):
    return await client.patch(
        f"/v1/admin/billing/plans/{tier}",
        json={"reason": "ajuste de teste", **fields},
        headers=headers,
    )


async def _patch_settings(client: AsyncClient, headers, **fields):
    return await client.patch(
        "/v1/admin/billing/settings",
        json={"reason": "ajuste de teste", **fields},
        headers=headers,
    )


class TestRecommendedValues:
    def test_pro_plan_follows_the_recommended_model(self):
        pro = RECOMMENDED_PLANS["pro"]
        fx = RECOMMENDED_SETTINGS["fx_rate_brl_per_usd"]

        assert pro["price_brl"] == 100.0
        assert pro["credits_brl"] == 120.0
        assert ceiling_usd(pro["credits_brl"], pro["cost_ratio"], fx) == pytest.approx(11.0)

    def test_every_plan_uses_the_same_real_cost_share(self):
        assert {plan["cost_ratio"] for plan in RECOMMENDED_PLANS.values()} == {0.55}

    def test_team_is_four_times_pro(self):
        assert RECOMMENDED_PLANS["team"]["price_brl"] == 4 * RECOMMENDED_PLANS["pro"]["price_brl"]
        assert (
            RECOMMENDED_PLANS["team"]["credits_brl"] == 4 * RECOMMENDED_PLANS["pro"]["credits_brl"]
        )


class TestMath:
    def test_worst_case_margin_of_the_pro_plan(self):
        assert margin_percent(100.0, 10.0, 66.0) == pytest.approx(24.0)

    def test_typical_usage_leaves_a_bigger_margin(self):
        assert margin_percent(100.0, 10.0, 66.0 * 0.6) == pytest.approx(50.4)

    def test_a_free_plan_has_no_margin(self):
        assert margin_percent(0.0, 10.0, 2.75) is None

    def test_a_loss_is_a_negative_margin(self):
        assert margin_percent(100.0, 10.0, 108.0) == pytest.approx(-18.0)

    def test_the_ceiling_follows_the_exchange_rate(self):
        assert ceiling_usd(120.0, 0.55, 6.0) == pytest.approx(11.0)
        assert ceiling_usd(120.0, 0.55, 5.5) == pytest.approx(12.0)

    @pytest.mark.parametrize(
        ("start", "months", "expected"),
        [
            (datetime(2026, 1, 31, tzinfo=UTC), 1, datetime(2026, 2, 28, tzinfo=UTC)),
            (datetime(2028, 1, 31, tzinfo=UTC), 1, datetime(2028, 2, 29, tzinfo=UTC)),
            (datetime(2026, 11, 15, tzinfo=UTC), 3, datetime(2027, 2, 15, tzinfo=UTC)),
            (datetime(2026, 3, 10, tzinfo=UTC), 12, datetime(2027, 3, 10, tzinfo=UTC)),
        ],
    )
    def test_adding_months_clamps_the_day(self, start, months, expected):
        assert add_months(start, months) == expected

    def test_the_next_month_rolls_over_the_year(self):
        assert next_month_start(datetime(2026, 12, 20, tzinfo=UTC)) == datetime(
            2027, 1, 1, tzinfo=UTC
        )
        assert next_month_start(datetime(2026, 5, 3, tzinfo=UTC)) == datetime(
            2026, 6, 1, tzinfo=UTC
        )


class TestStoredRules:
    async def test_first_use_creates_the_rows_from_the_recommended_values(self, session):
        pricing = await load_pricing(session)
        await session.commit()

        assert pricing.settings.fx_rate_brl_per_usd == 6.0
        assert pricing.plan("pro").ceiling_usd == pytest.approx(PRO_CEILING)
        assert pricing.plan("free").ceiling_usd == pytest.approx(FREE_CEILING)
        assert await session.get(BillingSetting, 1) is not None
        assert (
            await session.execute(select(func.count()).select_from(PlanPricing))
        ).scalar_one() == 3

    async def test_loading_twice_does_not_duplicate(self, session):
        await load_pricing(session)
        await session.commit()
        await load_pricing(session)
        await session.commit()

        assert (
            await session.execute(select(func.count()).select_from(PlanPricing))
        ).scalar_one() == 3

    async def test_saved_values_win_over_the_recommended_ones(self, session):
        await load_pricing(session)
        (await session.get(PlanPricing, "pro")).credits_brl = 240.0
        await session.commit()

        assert (await load_pricing(session)).plan("pro").ceiling_usd == pytest.approx(
            2 * PRO_CEILING
        )

    async def test_an_unknown_tier_falls_back_to_free(self, session):
        pricing = await load_pricing(session)

        assert pricing.plan("inexistente").tier == "free"


class TestSettlement:
    async def _setup(self, session):
        user = User(
            email=f"s-{uuid.uuid4().hex[:8]}@exemplo.com", password_hash="x", plan_tier="free"
        )
        session.add(user)
        await session.commit()

        return user, await load_pricing(session)

    async def test_overflow_is_charged_to_the_credit_that_expires_first(self, session):
        user, pricing = await self._setup(session)
        late = await grant_credit(
            session, user.id, credits_brl=10.0, price_paid_brl=10.0, pricing=pricing
        )
        soon = await grant_credit(
            session, user.id, credits_brl=10.0, price_paid_brl=10.0, pricing=pricing
        )
        soon.expires_at = datetime.now(UTC) + timedelta(days=5)
        before = soon.remaining_usd
        await _spend(session, user.id, FREE_CEILING + 0.2)

        await settle_overflow(session, user.id, FREE_CEILING)

        assert soon.remaining_usd == pytest.approx(before - 0.2)
        assert late.remaining_usd == pytest.approx(late.ceiling_usd)

    async def test_settling_twice_charges_once(self, session):
        user, pricing = await self._setup(session)
        grant = await grant_credit(
            session, user.id, credits_brl=10.0, price_paid_brl=10.0, pricing=pricing
        )
        await _spend(session, user.id, FREE_CEILING + 0.2)

        await settle_overflow(session, user.id, FREE_CEILING)
        await settle_overflow(session, user.id, FREE_CEILING)

        assert grant.remaining_usd == pytest.approx(grant.ceiling_usd - 0.2)

    async def test_new_spend_is_charged_incrementally(self, session):
        user, pricing = await self._setup(session)
        grant = await grant_credit(
            session, user.id, credits_brl=10.0, price_paid_brl=10.0, pricing=pricing
        )
        await _spend(session, user.id, FREE_CEILING + 0.1)
        await settle_overflow(session, user.id, FREE_CEILING)
        await _spend(session, user.id, 0.15)

        await settle_overflow(session, user.id, FREE_CEILING)

        assert grant.remaining_usd == pytest.approx(grant.ceiling_usd - 0.25)

    async def test_spend_within_the_plan_never_touches_credit(self, session):
        user, pricing = await self._setup(session)
        grant = await grant_credit(
            session, user.id, credits_brl=10.0, price_paid_brl=10.0, pricing=pricing
        )
        await _spend(session, user.id, FREE_CEILING - 0.05)

        await settle_overflow(session, user.id, FREE_CEILING)

        assert grant.remaining_usd == pytest.approx(grant.ceiling_usd)

    async def test_overflow_without_credit_is_forgiven(self, session):
        user, pricing = await self._setup(session)
        await _spend(session, user.id, FREE_CEILING + 0.3)
        await settle_overflow(session, user.id, FREE_CEILING)
        grant = await grant_credit(
            session, user.id, credits_brl=10.0, price_paid_brl=10.0, pricing=pricing
        )

        await settle_overflow(session, user.id, FREE_CEILING)

        assert grant.remaining_usd == pytest.approx(grant.ceiling_usd)

    async def test_expired_credit_is_ignored(self, session):
        user, pricing = await self._setup(session)
        grant = await grant_credit(
            session, user.id, credits_brl=10.0, price_paid_brl=10.0, pricing=pricing
        )
        grant.expires_at = datetime.now(UTC) - timedelta(days=1)
        await _spend(session, user.id, FREE_CEILING + 0.2)

        await settle_overflow(session, user.id, FREE_CEILING)
        balance = await balance_for(session, user.id, "free", pricing)

        assert grant.remaining_usd == pytest.approx(grant.ceiling_usd)
        assert balance.topups == []

    async def test_overflow_larger_than_one_credit_spills_to_the_next(self, session):
        user, pricing = await self._setup(session)
        first = await grant_credit(
            session, user.id, credits_brl=1.0, price_paid_brl=1.0, pricing=pricing
        )
        second = await grant_credit(
            session, user.id, credits_brl=10.0, price_paid_brl=10.0, pricing=pricing
        )
        first.expires_at = datetime.now(UTC) + timedelta(days=1)
        await _spend(session, user.id, FREE_CEILING + first.ceiling_usd + 0.1)

        await settle_overflow(session, user.id, FREE_CEILING)

        assert first.remaining_usd == pytest.approx(0.0)
        assert second.remaining_usd == pytest.approx(second.ceiling_usd - 0.1)

    async def test_a_new_month_starts_a_new_settlement(self, session):
        user, pricing = await self._setup(session)
        await _spend(session, user.id, FREE_CEILING + 0.1)

        await settle_overflow(session, user.id, FREE_CEILING)

        rows = (await session.execute(select(UsageSettlement))).scalars().all()
        assert len(rows) == 1
        assert rows[0].period == datetime.now(UTC).strftime("%Y-%m")


class TestCustomerUsage:
    async def test_a_new_free_account_sees_the_whole_balance(self, client: AsyncClient):
        headers, _ = await _register(client)

        usage = await _usage(client, headers)

        assert usage["plan_tier"] == "free"
        assert usage["plan_price_brl"] == 0.0
        assert usage["credits_total_brl"] == 5.0
        assert usage["credits_remaining_brl"] == 5.0
        assert usage["percent_used"] == 0.0
        assert usage["near_limit"] is False
        assert usage["exhausted"] is False
        assert usage["topups"] == []

    async def test_the_customer_never_sees_dollars(self, client: AsyncClient):
        headers, _ = await _register(client)

        usage = await _usage(client, headers)
        me = (await client.get("/v1/auth/me", headers=headers)).json()

        assert not [key for key in usage if "usd" in key]
        assert "monthly_cost_limit_usd" not in me["plan"]
        assert me["plan"]["price_brl"] == 0.0
        assert me["plan"]["credits_brl"] == 5.0

    async def test_the_pro_plan_shows_the_recommended_balance(self, client: AsyncClient, session):
        headers, email = await _register(client)
        await _set_plan(session, email, "pro")

        usage = await _usage(client, headers)

        assert usage["plan_price_brl"] == 100.0
        assert usage["credits_total_brl"] == 120.0

    async def test_the_balance_falls_in_proportion_to_the_real_cost(
        self, client: AsyncClient, session
    ):
        headers, email = await _register(client)
        await _set_plan(session, email, "pro")
        await _spend(session, (await _user(session, email)).id, PRO_CEILING / 2)

        usage = await _usage(client, headers)

        assert usage["credits_remaining_brl"] == pytest.approx(60.0, abs=0.01)
        assert usage["percent_used"] == pytest.approx(50.0, abs=0.1)

    async def test_the_limit_warning_follows_the_configured_threshold(
        self, client: AsyncClient, session
    ):
        headers, email = await _register(client)
        user_id = (await _user(session, email)).id

        await _spend(session, user_id, FREE_CEILING * 0.79)
        assert (await _usage(client, headers))["near_limit"] is False

        await _spend(session, user_id, FREE_CEILING * 0.02)
        assert (await _usage(client, headers))["near_limit"] is True

    async def test_an_exhausted_balance_blocks_new_jobs_in_reais(
        self, client: AsyncClient, session
    ):
        headers, email = await _register(client)
        await _spend(session, (await _user(session, email)).id, FREE_CEILING + 0.01)

        usage = await _usage(client, headers)
        response = await _create_job(client, headers)

        assert usage["exhausted"] is True
        assert usage["credits_remaining_brl"] == 0.0
        assert usage["percent_used"] == 100.0
        assert response.status_code == 402
        assert "creditos" in response.json()["message"]
        assert "US$" not in response.json()["message"]

    async def test_a_job_is_accepted_while_credit_remains(self, client: AsyncClient, session):
        headers, email = await _register(client)
        await _spend(session, (await _user(session, email)).id, FREE_CEILING * 0.9)

        assert (await _create_job(client, headers)).status_code == 202

    async def test_the_pack_list_comes_from_the_settings(self, client: AsyncClient, session):
        headers, _ = await _register(client)

        packs = (await _usage(client, headers))["packs"]

        assert packs == [
            {"price_brl": 30.0, "credits_brl": 30.0},
            {"price_brl": 60.0, "credits_brl": 60.0},
            {"price_brl": 100.0, "credits_brl": 100.0},
        ]

    async def test_the_period_and_renewal_are_reported(self, client: AsyncClient):
        headers, _ = await _register(client)

        usage = await _usage(client, headers)

        assert usage["period_start"] < usage["renews_at"]
        assert usage["renews_at"].endswith("Z") or "+00:00" in usage["renews_at"]

    async def test_it_requires_credentials(self, client: AsyncClient):
        assert (await client.get("/v1/usage")).status_code == 401

    async def test_one_account_never_sees_the_balance_of_another(
        self, client: AsyncClient, session
    ):
        spender, spender_email = await _register(client)
        other, _ = await _register(client)
        await _spend(session, (await _user(session, spender_email)).id, FREE_CEILING * 0.5)

        assert (await _usage(client, spender))["percent_used"] == pytest.approx(50.0, abs=0.1)
        assert (await _usage(client, other))["percent_used"] == 0.0

    async def test_the_public_plan_list_carries_the_prices(self, client: AsyncClient):
        plans = {plan["tier"]: plan for plan in (await client.get("/v1/meta/plans")).json()}

        assert plans["pro"]["price_brl"] == 100.0
        assert plans["team"]["credits_brl"] == 480.0
        assert all("monthly_cost_limit_usd" not in plan for plan in plans.values())


class TestAdminBilling:
    async def test_the_panel_shows_current_and_recommended_values(
        self, client: AsyncClient, session
    ):
        admin = await _admin(client, session)

        body = (await client.get("/v1/admin/billing", headers=admin)).json()

        assert body["settings"] == body["recommended_settings"]
        pro = next(plan for plan in body["plans"] if plan["tier"] == "pro")
        assert pro["ceiling_usd"] == pytest.approx(11.0)
        assert pro["worst_case_margin_percent"] == pytest.approx(24.0)
        assert pro["typical_margin_percent"] == pytest.approx(50.4)
        assert pro["margin_alert"] is False
        assert pro["recommended"] == RECOMMENDED_PLANS["pro"]

    async def test_a_free_plan_has_no_margin_to_alert_on(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        body = (await client.get("/v1/admin/billing", headers=admin)).json()
        free = next(plan for plan in body["plans"] if plan["tier"] == "free")

        assert free["worst_case_margin_percent"] is None
        assert free["margin_alert"] is False

    async def test_the_panel_reports_the_global_budget(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        body = (await client.get("/v1/admin/billing", headers=admin)).json()

        assert body["global_budget_usd"] > 0
        assert body["global_spend_usd"] == 0.0

    async def test_only_an_admin_session_reaches_it(self, client: AsyncClient, session):
        common, _ = await _register(client)
        routes = [
            ("get", "/v1/admin/billing", None),
            (
                "patch",
                "/v1/admin/billing/settings",
                {"reason": "teste de acesso", "fx_rate_brl_per_usd": 5},
            ),
            ("patch", "/v1/admin/billing/plans/pro", {"reason": "teste de acesso", "price_brl": 1}),
            (
                "post",
                f"/v1/admin/accounts/{uuid.uuid4()}/credits",
                {"reason": "teste de acesso", "price_brl": 10},
            ),
        ]

        for method, path, body in routes:
            response = await getattr(client, method)(
                path, headers=common, **({"json": body} if body else {})
            )
            assert response.status_code == 404, path

            anonymous = await getattr(client, method)(path, **({"json": body} if body else {}))
            assert anonymous.status_code == 401, path

    async def test_an_api_key_never_edits_prices(self, client: AsyncClient, session):
        headers, email = await _register(client)
        await _promote(session, email)
        key = (await client.post("/v1/auth/api-keys", json={"name": "ci"}, headers=headers)).json()[
            "api_key"
        ]

        response = await _patch_plan(client, {"Authorization": f"Bearer {key}"}, "pro", price_brl=1)

        assert response.status_code == 404

    async def test_changing_a_plan_moves_the_ceiling_at_once(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        headers, email = await _register(client)
        await _spend(session, (await _user(session, email)).id, FREE_CEILING + 0.1)
        assert (await _create_job(client, headers)).status_code == 402

        response = await _patch_plan(client, admin, "free", credits_brl=10.0)

        assert response.status_code == 200
        assert (await _create_job(client, headers)).status_code == 202

    async def test_lowering_the_credit_can_block_an_account(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        headers, email = await _register(client)
        await _set_plan(session, email, "pro")
        await _spend(session, (await _user(session, email)).id, 3.0)
        assert (await _create_job(client, headers)).status_code == 202

        await _patch_plan(client, admin, "pro", credits_brl=10.0)

        assert (await _create_job(client, headers)).status_code == 402

    async def test_a_cost_share_that_loses_money_raises_the_alert(
        self, client: AsyncClient, session
    ):
        admin = await _admin(client, session)

        body = (await _patch_plan(client, admin, "pro", cost_ratio=0.9)).json()
        pro = next(plan for plan in body["plans"] if plan["tier"] == "pro")

        assert pro["worst_case_margin_percent"] == pytest.approx(-18.0)
        assert pro["margin_alert"] is True

    async def test_the_alert_threshold_is_adjustable(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        body = (await _patch_settings(client, admin, min_margin_alert_percent=30.0)).json()
        pro = next(plan for plan in body["plans"] if plan["tier"] == "pro")

        assert pro["margin_alert"] is True

    async def test_the_exchange_rate_changes_every_ceiling(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        body = (await _patch_settings(client, admin, fx_rate_brl_per_usd=5.5)).json()
        pro = next(plan for plan in body["plans"] if plan["tier"] == "pro")

        assert pro["ceiling_usd"] == pytest.approx(12.0)
        assert body["settings"]["fx_rate_brl_per_usd"] == 5.5

    async def test_the_near_limit_warning_can_be_moved(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        headers, email = await _register(client)
        await _spend(session, (await _user(session, email)).id, FREE_CEILING * 0.5)
        assert (await _usage(client, headers))["near_limit"] is False

        await _patch_settings(client, admin, near_limit_percent=40.0)

        assert (await _usage(client, headers))["near_limit"] is True

    async def test_packs_are_sorted_and_deduplicated(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        body = (
            await _patch_settings(client, admin, topup_pack_prices_brl=[100, 45, 30.004, 60, 30])
        ).json()

        assert body["settings"]["topup_pack_prices_brl"] == [30.0, 45.0, 60.0, 100.0]

    async def test_the_topup_ratio_changes_what_a_pack_buys(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        headers, _ = await _register(client)

        await _patch_settings(client, admin, topup_credit_ratio=0.8)

        assert (await _usage(client, headers))["packs"][0] == {
            "price_brl": 30.0,
            "credits_brl": 24.0,
        }

    async def test_every_changed_field_leaves_its_own_audit_row(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        await _patch_plan(client, admin, "pro", price_brl=120.0, credits_brl=150.0)

        rows = (
            (
                await session.execute(
                    select(AdminAction).where(AdminAction.action == "plan_pricing_changed")
                )
            )
            .scalars()
            .all()
        )
        by_target = {row.target_email: row for row in rows}

        assert set(by_target) == {"plan:pro:price_brl", "plan:pro:credits_brl"}
        assert by_target["plan:pro:price_brl"].value_before == "100.0"
        assert by_target["plan:pro:price_brl"].value_after == "120.0"
        assert by_target["plan:pro:price_brl"].reason == "ajuste de teste"
        assert by_target["plan:pro:price_brl"].target_user_id is None

    async def test_untouched_fields_leave_no_audit_row(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        await _patch_plan(client, admin, "pro", price_brl=120.0, credits_brl=120.0)

        rows = (
            await session.execute(
                select(func.count())
                .select_from(AdminAction)
                .where(AdminAction.action == "plan_pricing_changed")
            )
        ).scalar_one()
        assert rows == 1

    async def test_the_audit_list_shows_the_configuration_changes(
        self, client: AsyncClient, session
    ):
        admin = await _admin(client, session)
        await _patch_settings(client, admin, fees_tax_percent=12.0)

        audit = (await client.get("/v1/admin/audit", headers=admin)).json()

        entry = next(item for item in audit if item["action"] == "billing_setting_changed")
        assert entry["target_email"] == "billing:fees_tax_percent"
        assert (entry["value_before"], entry["value_after"]) == ("10.0", "12.0")

    async def test_a_change_that_changes_nothing_is_refused(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        response = await _patch_plan(client, admin, "pro", price_brl=100.0)

        assert response.status_code == 422
        assert response.json()["message"] == "Nenhum valor mudou."

    async def test_a_request_without_fields_is_refused(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        assert (await _patch_settings(client, admin)).status_code == 422

    @pytest.mark.parametrize(
        "fields",
        [
            {"fx_rate_brl_per_usd": 0},
            {"fx_rate_brl_per_usd": -1},
            {"fx_rate_brl_per_usd": 1000},
            {"fees_tax_percent": -1},
            {"fees_tax_percent": 61},
            {"topup_credit_ratio": 0},
            {"topup_cost_ratio": 0},
            {"topup_cost_ratio": 1.5},
            {"topup_validity_months": 0},
            {"topup_validity_months": 61},
            {"topup_pack_prices_brl": []},
            {"topup_pack_prices_brl": [0]},
            {"topup_pack_prices_brl": [-5, 10]},
            {"near_limit_percent": 0},
            {"near_limit_percent": 101},
            {"min_margin_alert_percent": 101},
            {"typical_usage_percent": 0},
        ],
    )
    async def test_invalid_settings_are_rejected(self, client: AsyncClient, session, fields):
        admin = await _admin(client, session)

        response = await _patch_settings(client, admin, **fields)

        assert response.status_code == 422, fields

    @pytest.mark.parametrize(
        "fields",
        [
            {"price_brl": -1},
            {"credits_brl": 0},
            {"cost_ratio": 0},
            {"cost_ratio": 1.01},
        ],
    )
    async def test_invalid_plan_values_are_rejected(self, client: AsyncClient, session, fields):
        admin = await _admin(client, session)

        assert (await _patch_plan(client, admin, "pro", **fields)).status_code == 422

    async def test_a_reason_is_mandatory(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        for reason in ("", "abc", "      "):
            response = await client.patch(
                "/v1/admin/billing/plans/pro",
                json={"reason": reason, "price_brl": 150.0},
                headers=admin,
            )
            assert response.status_code == 422

        no_reason = await client.patch(
            "/v1/admin/billing/plans/pro", json={"price_brl": 150.0}, headers=admin
        )
        assert no_reason.status_code == 422

    async def test_a_rejected_change_changes_nothing(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        await _patch_plan(client, admin, "pro", price_brl=150.0, cost_ratio=5)
        body = (await client.get("/v1/admin/billing", headers=admin)).json()

        assert next(p for p in body["plans"] if p["tier"] == "pro")["price_brl"] == 100.0

    async def test_an_unknown_plan_is_not_found(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        assert (await _patch_plan(client, admin, "platinum", price_brl=1.0)).status_code == 404

    async def test_resetting_to_the_recommended_value_works(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        await _patch_settings(client, admin, fx_rate_brl_per_usd=5.0)

        body = (
            await _patch_settings(
                client, admin, fx_rate_brl_per_usd=RECOMMENDED_SETTINGS["fx_rate_brl_per_usd"]
            )
        ).json()

        assert body["settings"] == body["recommended_settings"]


class TestCredits:
    async def _target(self, client: AsyncClient, session):
        headers, email = await _register(client)

        return headers, email, (await _user(session, email)).id

    async def _grant(self, client: AsyncClient, admin, user_id, **fields):
        return await client.post(
            f"/v1/admin/accounts/{user_id}/credits",
            json={"reason": "recarga de teste", **fields},
            headers=admin,
        )

    async def test_a_paid_top_up_buys_credit_at_the_configured_ratio(
        self, client: AsyncClient, session
    ):
        admin = await _admin(client, session)
        headers, _, user_id = await self._target(client, session)

        response = await self._grant(client, admin, user_id, price_brl=100.0)

        assert response.status_code == 201
        assert response.json()["credits_brl"] == 100.0
        usage = await _usage(client, headers)
        assert usage["credits_total_brl"] == 105.0
        assert usage["credits_remaining_brl"] == 105.0
        assert usage["topups"][0]["credits_brl"] == 100.0

    async def test_a_courtesy_grant_takes_the_credit_directly(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        _, _, user_id = await self._target(client, session)

        response = await self._grant(client, admin, user_id, credits_brl=25.5)

        assert response.json()["credits_brl"] == 25.5
        grant = (await session.execute(select(CreditGrant))).scalars().one()
        assert grant.price_paid_brl is None

    async def test_the_real_cost_of_a_top_up_uses_the_top_up_share(
        self, client: AsyncClient, session
    ):
        admin = await _admin(client, session)
        _, _, user_id = await self._target(client, session)

        await self._grant(client, admin, user_id, price_brl=100.0)

        grant = (await session.execute(select(CreditGrant))).scalars().one()
        assert grant.ceiling_usd == pytest.approx(100.0 * 0.55 / 6.0)
        assert grant.price_paid_brl == 100.0

    async def test_the_validity_comes_from_the_settings(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        _, _, user_id = await self._target(client, session)
        await _patch_settings(client, admin, topup_validity_months=3)

        await self._grant(client, admin, user_id, price_brl=30.0)

        grant = (await session.execute(select(CreditGrant))).scalars().one()
        expires = (
            grant.expires_at if grant.expires_at.tzinfo else grant.expires_at.replace(tzinfo=UTC)
        )
        assert abs(expires - add_months(datetime.now(UTC), 3)) < timedelta(minutes=1)

    async def test_the_grant_must_say_whether_it_was_paid(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        _, _, user_id = await self._target(client, session)

        both = await self._grant(client, admin, user_id, price_brl=10.0, credits_brl=10.0)
        neither = await self._grant(client, admin, user_id)

        assert both.status_code == 422
        assert neither.status_code == 422
        assert (
            await session.execute(select(func.count()).select_from(CreditGrant))
        ).scalar_one() == 0

    @pytest.mark.parametrize("fields", [{"price_brl": 0}, {"price_brl": -5}, {"credits_brl": 0}])
    async def test_non_positive_amounts_are_rejected(self, client: AsyncClient, session, fields):
        admin = await _admin(client, session)
        _, _, user_id = await self._target(client, session)

        assert (await self._grant(client, admin, user_id, **fields)).status_code == 422

    async def test_an_unknown_account_is_not_found(self, client: AsyncClient, session):
        admin = await _admin(client, session)

        assert (await self._grant(client, admin, uuid.uuid4(), price_brl=10.0)).status_code == 404

    async def test_credit_lets_an_exhausted_account_work_again(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        headers, _, user_id = await self._target(client, session)
        await _spend(session, user_id, FREE_CEILING + 0.05)
        assert (await _create_job(client, headers)).status_code == 402

        await self._grant(client, admin, user_id, price_brl=30.0)

        assert (await _create_job(client, headers)).status_code == 202

    async def test_credit_is_used_only_after_the_plan_allowance(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        headers, _, user_id = await self._target(client, session)
        await self._grant(client, admin, user_id, price_brl=30.0)

        await _spend(session, user_id, FREE_CEILING * 0.5)
        within_plan = await _usage(client, headers)

        assert within_plan["topups"][0]["remaining_brl"] == 30.0
        assert within_plan["plan_credits_remaining_brl"] == pytest.approx(2.5, abs=0.01)

        await _spend(session, user_id, FREE_CEILING * 0.5 + (30.0 * 0.55 / 6.0) / 2)
        beyond_plan = await _usage(client, headers)

        assert beyond_plan["plan_credits_remaining_brl"] == 0.0
        assert beyond_plan["topups"][0]["remaining_brl"] == pytest.approx(15.0, abs=0.05)
        assert beyond_plan["exhausted"] is False

    async def test_credit_that_runs_out_blocks_again(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        headers, _, user_id = await self._target(client, session)
        await self._grant(client, admin, user_id, price_brl=30.0)

        await _spend(session, user_id, FREE_CEILING + (30.0 * 0.55 / 6.0) + 0.01)

        assert (await _usage(client, headers))["exhausted"] is True
        assert (await _create_job(client, headers)).status_code == 402

    async def test_credit_of_one_account_never_helps_another(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        _, _, rich_id = await self._target(client, session)
        poor_headers, _, poor_id = await self._target(client, session)
        await self._grant(client, admin, rich_id, price_brl=100.0)
        await _spend(session, poor_id, FREE_CEILING + 0.05)

        assert (await _create_job(client, poor_headers)).status_code == 402

    async def test_expired_credit_stops_counting(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        headers, _, user_id = await self._target(client, session)
        await self._grant(client, admin, user_id, price_brl=30.0)
        grant = (await session.execute(select(CreditGrant))).scalars().one()
        grant.expires_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()

        usage = await _usage(client, headers)

        assert usage["topups"] == []
        assert usage["credits_total_brl"] == 5.0

    async def test_the_grant_is_audited_against_the_account(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        _, email, user_id = await self._target(client, session)

        await self._grant(client, admin, user_id, price_brl=60.0)

        action = (
            await session.execute(select(AdminAction).where(AdminAction.action == "credit_granted"))
        ).scalar_one()
        assert action.target_email == email
        assert action.value_after == "R$ 60.00"
        assert action.reason == "recarga de teste"

    async def test_the_account_list_shows_the_remaining_credit(self, client: AsyncClient, session):
        admin = await _admin(client, session)
        _, email, user_id = await self._target(client, session)
        await self._grant(client, admin, user_id, price_brl=30.0)

        accounts = (await client.get(f"/v1/admin/accounts?search={email}", headers=admin)).json()
        account = accounts["items"][0]

        assert account["credits_remaining_brl"] == pytest.approx(35.0)
        assert account["cost_limit_usd"] == pytest.approx(FREE_CEILING, abs=1e-3)

    async def test_the_grant_response_returns_the_updated_account(
        self, client: AsyncClient, session
    ):
        admin = await _admin(client, session)
        _, email, user_id = await self._target(client, session)

        body = (await self._grant(client, admin, user_id, credits_brl=10.0)).json()

        assert body["account"]["email"] == email
        assert body["account"]["credits_remaining_brl"] == pytest.approx(15.0)
