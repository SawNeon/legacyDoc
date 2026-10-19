"""Credit balance shown to the customer, in reais and never in dollars."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from legacydoc_core.billing import balance_for, load_pricing, month_start, next_month_start
from legacydoc_core.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from legacydoc_api.deps import Principal, count_jobs_this_month, get_principal
from legacydoc_api.schemas import UsagePack, UsageResponse, UsageTopup

router = APIRouter(prefix="/v1/usage", tags=["usage"])


@router.get("", response_model=UsageResponse)
async def get_usage(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> UsageResponse:
    """Remaining credit, how much of it is used and what a top-up costs."""
    pricing = await load_pricing(session)
    balance = await balance_for(session, principal.id, principal.user.plan_tier, pricing)
    rules = pricing.settings

    return UsageResponse(
        plan_tier=str(principal.plan.tier),
        plan_name=principal.plan.display_name,
        plan_price_brl=balance.plan.price_brl,
        credits_total_brl=round(balance.credits_total_brl, 2),
        credits_remaining_brl=round(balance.credits_remaining_brl, 2),
        plan_credits_remaining_brl=round(balance.plan_credits_remaining_brl, 2),
        percent_used=round(balance.percent_used, 1),
        near_limit=balance.percent_used >= rules.near_limit_percent,
        exhausted=balance.available_usd <= 0,
        period_start=month_start(),
        renews_at=next_month_start(),
        jobs_used_this_month=await count_jobs_this_month(session, principal.id),
        monthly_job_quota=principal.plan.monthly_job_quota,
        topups=[
            UsageTopup(
                credits_brl=round(topup.credits_brl, 2),
                remaining_brl=round(topup.remaining_brl, 2),
                expires_at=topup.expires_at,
            )
            for topup in balance.topups
        ],
        packs=[
            UsagePack(price_brl=price, credits_brl=round(price * rules.topup_credit_ratio, 2))
            for price in rules.topup_pack_prices_brl
        ],
    )
