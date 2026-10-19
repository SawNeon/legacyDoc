"""Plan description shared by the routes that expose it."""

from __future__ import annotations

from legacydoc_core.billing import Pricing
from legacydoc_core.plans import PlanLimits

from legacydoc_api.schemas import PlanInfo


def plan_info(plan: PlanLimits, pricing: Pricing) -> PlanInfo:
    priced = pricing.plan(str(plan.tier))

    return PlanInfo(
        tier=str(plan.tier),
        display_name=plan.display_name,
        monthly_job_quota=plan.monthly_job_quota,
        price_brl=priced.price_brl,
        credits_brl=priced.credits_brl,
        max_files_per_job=plan.max_files_per_job,
        max_concurrent_jobs=plan.max_concurrent_jobs,
        features=sorted(str(feature) for feature in plan.features),
        max_depth=str(plan.max_depth),
        available_depths=[str(depth) for depth in plan.available_depths],
    )
