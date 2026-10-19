"""Pricing rules read from the database, credit balance and overflow settlement."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from legacydoc_core.models import (
    BillingSetting,
    CreditGrant,
    PlanPricing,
    UsageRecord,
    UsageSettlement,
)
from legacydoc_core.plans import PlanTier

RECOMMENDED_SETTINGS: dict[str, float | int | list[float]] = {
    "fx_rate_brl_per_usd": 6.0,
    "fees_tax_percent": 10.0,
    "topup_credit_ratio": 1.0,
    "topup_cost_ratio": 0.55,
    "topup_validity_months": 12,
    "topup_pack_prices_brl": [30.0, 60.0, 100.0],
    "near_limit_percent": 80.0,
    "min_margin_alert_percent": 15.0,
    "typical_usage_percent": 60.0,
}

RECOMMENDED_PLANS: dict[str, dict[str, float]] = {
    "free": {"price_brl": 0.0, "credits_brl": 5.0, "cost_ratio": 0.55},
    "pro": {"price_brl": 100.0, "credits_brl": 120.0, "cost_ratio": 0.55},
    "team": {"price_brl": 400.0, "credits_brl": 480.0, "cost_ratio": 0.55},
}


@dataclass(frozen=True)
class BillingRules:
    fx_rate_brl_per_usd: float
    fees_tax_percent: float
    topup_credit_ratio: float
    topup_cost_ratio: float
    topup_validity_months: int
    topup_pack_prices_brl: list[float]
    near_limit_percent: float
    min_margin_alert_percent: float
    typical_usage_percent: float


@dataclass(frozen=True)
class Plan:
    tier: str
    price_brl: float
    credits_brl: float
    cost_ratio: float
    ceiling_usd: float
    worst_case_margin_percent: float | None
    typical_margin_percent: float | None


@dataclass(frozen=True)
class Pricing:
    settings: BillingRules
    plans: dict[str, Plan]

    def plan(self, tier: str) -> Plan:
        return self.plans.get(tier) or self.plans[str(PlanTier.FREE)]


def ceiling_usd(credits_brl: float, cost_ratio: float, fx_rate: float) -> float:
    return credits_brl * cost_ratio / fx_rate


def margin_percent(price_brl: float, fees_percent: float, cost_brl: float) -> float | None:
    if price_brl <= 0:
        return None

    return (price_brl - price_brl * fees_percent / 100 - cost_brl) / price_brl * 100


def _build_plan(tier: str, row: PlanPricing, settings: BillingRules) -> Plan:
    ceiling = ceiling_usd(row.credits_brl, row.cost_ratio, settings.fx_rate_brl_per_usd)
    worst_cost = ceiling * settings.fx_rate_brl_per_usd
    typical_cost = worst_cost * settings.typical_usage_percent / 100

    return Plan(
        tier=tier,
        price_brl=row.price_brl,
        credits_brl=row.credits_brl,
        cost_ratio=row.cost_ratio,
        ceiling_usd=ceiling,
        worst_case_margin_percent=margin_percent(
            row.price_brl, settings.fees_tax_percent, worst_cost
        ),
        typical_margin_percent=margin_percent(
            row.price_brl, settings.fees_tax_percent, typical_cost
        ),
    )


async def _ensure_rows(session: AsyncSession) -> None:
    settings_row = await session.get(BillingSetting, 1)
    existing_tiers = set((await session.execute(select(PlanPricing.tier))).scalars())
    missing = [tier for tier in RECOMMENDED_PLANS if tier not in existing_tiers]

    if settings_row is not None and not missing:
        return

    try:
        async with session.begin_nested():
            if settings_row is None:
                session.add(BillingSetting(id=1, **RECOMMENDED_SETTINGS))

            for tier in missing:
                session.add(PlanPricing(tier=tier, **RECOMMENDED_PLANS[tier]))

            await session.flush()
    except IntegrityError:
        pass


async def load_pricing(session: AsyncSession) -> Pricing:
    """Current rules. Missing rows are created from the recommended values on first use."""
    await _ensure_rows(session)

    row = await session.get(BillingSetting, 1)
    assert row is not None

    settings = BillingRules(
        fx_rate_brl_per_usd=row.fx_rate_brl_per_usd,
        fees_tax_percent=row.fees_tax_percent,
        topup_credit_ratio=row.topup_credit_ratio,
        topup_cost_ratio=row.topup_cost_ratio,
        topup_validity_months=row.topup_validity_months,
        topup_pack_prices_brl=[float(price) for price in row.topup_pack_prices_brl],
        near_limit_percent=row.near_limit_percent,
        min_margin_alert_percent=row.min_margin_alert_percent,
        typical_usage_percent=row.typical_usage_percent,
    )

    rows = (await session.execute(select(PlanPricing))).scalars()

    return Pricing(
        settings=settings,
        plans={plan.tier: _build_plan(plan.tier, plan, settings) for plan in rows},
    )


def month_start(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(UTC)

    return datetime(moment.year, moment.month, 1, tzinfo=UTC)


def next_month_start(now: datetime | None = None) -> datetime:
    start = month_start(now)

    return datetime(start.year + (start.month // 12), start.month % 12 + 1, 1, tzinfo=UTC)


def period_key(now: datetime | None = None) -> str:
    return month_start(now).strftime("%Y-%m")


def add_months(moment: datetime, months: int) -> datetime:
    index = moment.month - 1 + months
    year = moment.year + index // 12
    month = index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])

    return moment.replace(year=year, month=month, day=day)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def spend_in_month(session: AsyncSession, user_id) -> float:
    result = await session.execute(
        select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0)).where(
            UsageRecord.user_id == user_id, UsageRecord.created_at >= month_start()
        )
    )

    return float(result.scalar_one())


async def _active_grants(
    session: AsyncSession, user_id, *, lock: bool = False
) -> list[CreditGrant]:
    query = (
        select(CreditGrant)
        .where(CreditGrant.user_id == user_id, CreditGrant.remaining_usd > 0)
        .order_by(CreditGrant.expires_at.asc(), CreditGrant.created_at.asc())
    )

    if lock:
        query = query.with_for_update()

    now = datetime.now(UTC)
    grants = (await session.execute(query)).scalars().all()

    return [grant for grant in grants if _aware(grant.expires_at) > now]


async def settle_overflow(session: AsyncSession, user_id, plan_ceiling_usd: float) -> None:
    """Charge spend beyond the plan allowance to the oldest-expiring credits.

    Overflow that no credit can cover is forgiven: it is slack in the pre-job
    check, and carrying it as debt would swallow the next credit the account buys.
    """
    spent = await spend_in_month(session, user_id)
    overflow = max(0.0, spent - plan_ceiling_usd)
    period = period_key()

    settlement = (
        await session.execute(
            select(UsageSettlement)
            .where(UsageSettlement.user_id == user_id, UsageSettlement.period == period)
            .with_for_update()
        )
    ).scalar_one_or_none()

    if settlement is None:
        settlement = UsageSettlement(user_id=user_id, period=period, settled_usd=0.0)
        session.add(settlement)

    pending = overflow - settlement.settled_usd

    if pending <= 0:
        return

    for grant in await _active_grants(session, user_id, lock=True):
        if pending <= 0:
            break

        taken = min(grant.remaining_usd, pending)
        grant.remaining_usd -= taken
        pending -= taken

    settlement.settled_usd = overflow
    await session.flush()


@dataclass(frozen=True)
class TopupBalance:
    credits_brl: float
    remaining_brl: float
    expires_at: datetime


@dataclass(frozen=True)
class Balance:
    plan: Plan
    spent_usd: float
    plan_remaining_usd: float
    topup_remaining_usd: float
    credits_total_brl: float
    credits_remaining_brl: float
    plan_credits_remaining_brl: float
    topups: list[TopupBalance]

    @property
    def available_usd(self) -> float:
        return self.plan_remaining_usd + self.topup_remaining_usd

    @property
    def percent_used(self) -> float:
        if self.credits_total_brl <= 0:
            return 100.0

        return max(0.0, min(100.0, (1 - self.credits_remaining_brl / self.credits_total_brl) * 100))


async def balance_for(session: AsyncSession, user_id, tier: str, pricing: Pricing) -> Balance:
    plan = pricing.plan(tier)

    await settle_overflow(session, user_id, plan.ceiling_usd)

    spent = await spend_in_month(session, user_id)
    plan_remaining = max(0.0, plan.ceiling_usd - spent)
    plan_fraction = plan_remaining / plan.ceiling_usd if plan.ceiling_usd > 0 else 0.0
    plan_credits_remaining = plan.credits_brl * plan_fraction

    grants = await _active_grants(session, user_id)
    topups = [
        TopupBalance(
            credits_brl=grant.credits_brl,
            remaining_brl=grant.credits_brl * grant.remaining_usd / grant.ceiling_usd
            if grant.ceiling_usd > 0
            else 0.0,
            expires_at=grant.expires_at,
        )
        for grant in grants
    ]

    return Balance(
        plan=plan,
        spent_usd=spent,
        plan_remaining_usd=plan_remaining,
        topup_remaining_usd=sum(grant.remaining_usd for grant in grants),
        credits_total_brl=plan.credits_brl + sum(topup.credits_brl for topup in topups),
        credits_remaining_brl=plan_credits_remaining + sum(topup.remaining_brl for topup in topups),
        plan_credits_remaining_brl=plan_credits_remaining,
        topups=topups,
    )


async def grant_credit(
    session: AsyncSession,
    user_id,
    *,
    credits_brl: float,
    price_paid_brl: float | None,
    pricing: Pricing,
) -> CreditGrant:
    settings = pricing.settings
    grant = CreditGrant(
        user_id=user_id,
        credits_brl=credits_brl,
        ceiling_usd=ceiling_usd(
            credits_brl, settings.topup_cost_ratio, settings.fx_rate_brl_per_usd
        ),
        price_paid_brl=price_paid_brl,
        expires_at=add_months(datetime.now(UTC), settings.topup_validity_months),
    )
    grant.remaining_usd = grant.ceiling_usd

    session.add(grant)
    await session.flush()

    return grant
