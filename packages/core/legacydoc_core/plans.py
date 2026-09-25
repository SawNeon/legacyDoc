"""Commercial plans: quotas, features and per-tier limits."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PlanTier(StrEnum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"


class GenerationDepth(StrEnum):
    """How much analysis a single job asks for."""

    BASIC = "basic"

    STANDARD = "standard"

    PRO = "pro"

    @property
    def rank(self) -> int:
        return DEPTH_ORDER.index(self)

    @property
    def runs_improver(self) -> bool:
        return self.rank >= GenerationDepth.STANDARD.rank

    @property
    def runs_verifier(self) -> bool:
        return self.rank >= GenerationDepth.PRO.rank


DEPTH_ORDER: tuple[GenerationDepth, ...] = (
    GenerationDepth.BASIC,
    GenerationDepth.STANDARD,
    GenerationDepth.PRO,
)


class Feature(StrEnum):
    """Capacidades liberadas por plano."""

    DOCUMENTATION = "documentation"

    IMPROVEMENT_FINDINGS = "improvement_findings"

    SECURITY_FINDINGS = "security_findings"

    PROJECT_CONTEXT = "project_context"

    CUSTOM_PROVIDER_ROUTING = "custom_provider_routing"

    WEBHOOKS = "webhooks"

    PRIORITY_QUEUE = "priority_queue"


@dataclass(frozen=True)
class PlanLimits:
    tier: PlanTier
    display_name: str
    monthly_job_quota: int

    monthly_cost_limit_usd: float

    max_files_per_job: int
    max_concurrent_jobs: int
    queue_priority: int

    max_depth: GenerationDepth = GenerationDepth.BASIC

    features: frozenset[Feature] = field(default_factory=frozenset)

    def allows(self, feature: Feature) -> bool:
        return feature in self.features

    @property
    def available_depths(self) -> list[GenerationDepth]:
        """Every depth this plan may pick, cheapest first."""
        return [depth for depth in DEPTH_ORDER if depth.rank <= self.max_depth.rank]


_FREE = PlanLimits(
    tier=PlanTier.FREE,
    display_name="Free",
    monthly_job_quota=20,
    monthly_cost_limit_usd=0.50,
    max_files_per_job=3,
    max_concurrent_jobs=1,
    queue_priority=100,
    max_depth=GenerationDepth.BASIC,
    features=frozenset({Feature.DOCUMENTATION}),
)

_PRO = PlanLimits(
    tier=PlanTier.PRO,
    display_name="Pro",
    monthly_job_quota=500,
    monthly_cost_limit_usd=25.00,
    max_files_per_job=50,
    max_concurrent_jobs=4,
    queue_priority=50,
    max_depth=GenerationDepth.PRO,
    features=frozenset(
        {
            Feature.DOCUMENTATION,
            Feature.IMPROVEMENT_FINDINGS,
            Feature.SECURITY_FINDINGS,
            Feature.PROJECT_CONTEXT,
            Feature.WEBHOOKS,
        }
    ),
)

_TEAM = PlanLimits(
    tier=PlanTier.TEAM,
    display_name="Team",
    monthly_job_quota=5000,
    monthly_cost_limit_usd=200.00,
    max_files_per_job=500,
    max_concurrent_jobs=16,
    queue_priority=10,
    max_depth=GenerationDepth.PRO,
    features=frozenset(
        {
            Feature.DOCUMENTATION,
            Feature.IMPROVEMENT_FINDINGS,
            Feature.SECURITY_FINDINGS,
            Feature.PROJECT_CONTEXT,
            Feature.CUSTOM_PROVIDER_ROUTING,
            Feature.WEBHOOKS,
            Feature.PRIORITY_QUEUE,
        }
    ),
)

PLANS: dict[PlanTier, PlanLimits] = {
    PlanTier.FREE: _FREE,
    PlanTier.PRO: _PRO,
    PlanTier.TEAM: _TEAM,
}


def get_plan(tier: PlanTier | str) -> PlanLimits:
    """Resolve a tier to its limits, falling back to FREE when unknown."""
    try:
        return PLANS[PlanTier(tier)]
    except ValueError:
        return PLANS[PlanTier.FREE]


def resolve_depth(requested: GenerationDepth | str | None, plan: PlanLimits) -> GenerationDepth:
    """The depth a job actually runs at: what was asked, capped by the plan."""
    if requested is None:
        return plan.max_depth

    try:
        depth = GenerationDepth(requested)
    except ValueError:
        return plan.max_depth

    return depth if depth.rank <= plan.max_depth.rank else plan.max_depth
