"""Commercial plans: quotas, features and per-tier limits.

Single source of truth for what each plan unlocks. The API reads it to decide
402/403 and the worker reads it to choose which agents run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PlanTier(StrEnum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"


class Feature(StrEnum):
    """Capacidades liberadas por plano."""

    DOCUMENTATION = "documentation"
    """Geracao de documentacao. Presente em todos os planos."""

    IMPROVEMENT_FINDINGS = "improvement_findings"
    """Pontos de melhoria: complexidade, code smells, riscos."""

    SECURITY_FINDINGS = "security_findings"
    """Subconjunto dos findings focado em risco de seguranca."""

    PROJECT_CONTEXT = "project_context"
    """API de contexto: glossario, ADRs e convencoes injetados nos prompts."""

    VERIFIER_AGENT = "verifier_agent"
    """Passo de auditoria que reprova e reescreve documentacao infiel."""

    CUSTOM_PROVIDER_ROUTING = "custom_provider_routing"
    """Cliente escolhe provedor/modelo por agente."""

    WEBHOOKS = "webhooks"
    """Callback HTTP quando o job termina."""

    PRIORITY_QUEUE = "priority_queue"
    """Jobs entram na frente na fila."""


@dataclass(frozen=True)
class PlanLimits:
    tier: PlanTier
    display_name: str
    monthly_job_quota: int

    monthly_cost_limit_usd: float
    """Real LLM spend ceiling per user per month.

    A job count quota protects nothing: one file and five hundred files differ
    by orders of magnitude. The bill is in dollars, so the limit is too.
    """

    max_files_per_job: int
    max_concurrent_jobs: int
    queue_priority: int
    """Lower values are served first."""
    features: frozenset[Feature] = field(default_factory=frozenset)

    def allows(self, feature: Feature) -> bool:
        return feature in self.features


_FREE = PlanLimits(
    tier=PlanTier.FREE,
    display_name="Free",
    monthly_job_quota=20,
    # 20 jobs x 3 files x ~US$0.002 leaves headroom for large files.
    monthly_cost_limit_usd=0.50,
    max_files_per_job=3,
    max_concurrent_jobs=1,
    queue_priority=100,
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
    features=frozenset(
        {
            Feature.DOCUMENTATION,
            Feature.IMPROVEMENT_FINDINGS,
            Feature.SECURITY_FINDINGS,
            Feature.PROJECT_CONTEXT,
            Feature.VERIFIER_AGENT,
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
    features=frozenset(
        {
            Feature.DOCUMENTATION,
            Feature.IMPROVEMENT_FINDINGS,
            Feature.SECURITY_FINDINGS,
            Feature.PROJECT_CONTEXT,
            Feature.VERIFIER_AGENT,
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
