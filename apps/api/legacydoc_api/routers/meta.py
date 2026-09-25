"""Public metadata: languages, plans and export formats."""

from __future__ import annotations

from fastapi import APIRouter
from legacydoc_core.plans import PLANS
from legacydoc_exporters import ExporterFactory
from legacydoc_parsing.languages import LANGUAGES, extensions_by_language

from legacydoc_api.schemas import LanguageResponse, PlanInfo

router = APIRouter(prefix="/v1/meta", tags=["meta"])


@router.get("/languages", response_model=list[LanguageResponse])
async def list_languages() -> list[LanguageResponse]:
    by_language = extensions_by_language()

    return [
        LanguageResponse(
            name=info.name,
            display_name=info.display_name,
            extensions=by_language.get(key, []),
        )
        for key, info in sorted(LANGUAGES.items())
    ]


@router.get("/plans", response_model=list[PlanInfo])
async def list_plans() -> list[PlanInfo]:
    return [
        PlanInfo(
            tier=str(plan.tier),
            display_name=plan.display_name,
            monthly_job_quota=plan.monthly_job_quota,
            monthly_cost_limit_usd=plan.monthly_cost_limit_usd,
            max_files_per_job=plan.max_files_per_job,
            max_concurrent_jobs=plan.max_concurrent_jobs,
            features=sorted(str(feature) for feature in plan.features),
            max_depth=str(plan.max_depth),
            available_depths=[str(depth) for depth in plan.available_depths],
        )
        for plan in PLANS.values()
    ]


@router.get("/export-formats", response_model=list[str])
async def list_export_formats() -> list[str]:
    return ExporterFactory.available_formats()
