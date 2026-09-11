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


class GenerationDepth(StrEnum):
    """How much analysis a single job asks for.

    Separate from the plan on purpose. The plan says how deep a customer *may*
    go; this says how deep they *chose* to go on this job. Someone on a paid
    plan documenting a whole legacy repository usually wants the cheap pass
    over three hundred files, not the audited one, and without this the only
    way to spend less was to stop using the product.
    """

    BASIC = "basic"
    """Writer and summarizer. One model call per chunk, the cheapest useful output."""

    STANDARD = "standard"
    """Adds the improver, which produces the improvement findings."""

    PRO = "pro"
    """Adds the verifier, which audits the documentation against the source
    and sends unfaithful symbols back to be rewritten. Roughly seventy percent
    of the cost of a job sits in this step."""

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
    """Geracao de documentacao. Presente em todos os planos."""

    IMPROVEMENT_FINDINGS = "improvement_findings"
    """Ver os pontos de melhoria ja gravados.

    Permissao de leitura, nao de geracao: quem gera e a profundidade escolhida
    no job. Separado de proposito, para que um upgrade revele analise que ja
    esta no banco sem reprocessar nem cobrar token de novo.
    """

    SECURITY_FINDINGS = "security_findings"
    """Subconjunto dos findings focado em risco de seguranca."""

    PROJECT_CONTEXT = "project_context"
    """API de contexto: glossario, ADRs e convencoes injetados nos prompts."""

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

    max_depth: GenerationDepth = GenerationDepth.BASIC
    """Deepest analysis this plan may request, and the default when none is asked."""

    features: frozenset[Feature] = field(default_factory=frozenset)

    def allows(self, feature: Feature) -> bool:
        return feature in self.features

    @property
    def available_depths(self) -> list[GenerationDepth]:
        """Every depth this plan may pick, cheapest first.

        Exposed through the API so the front can build the selector without
        hardcoding the ordering and drifting from the backend.
        """
        return [depth for depth in DEPTH_ORDER if depth.rank <= self.max_depth.rank]


_FREE = PlanLimits(
    tier=PlanTier.FREE,
    display_name="Free",
    monthly_job_quota=20,
    # 20 jobs x 3 files x ~US$0.002 leaves headroom for large files.
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
    """The depth a job actually runs at: what was asked, capped by the plan.

    Caps instead of refusing. A client that always asks for the deepest pass
    still works on every plan, and the effective depth comes back in the job
    and document responses, so nobody has to guess what they got.

    Called again by the worker rather than trusted from the stored parameters,
    because a job can sit in the queue while the account changes plan.
    """
    if requested is None:
        return plan.max_depth

    try:
        depth = GenerationDepth(requested)
    except ValueError:
        return plan.max_depth

    return depth if depth.rank <= plan.max_depth.rank else plan.max_depth
