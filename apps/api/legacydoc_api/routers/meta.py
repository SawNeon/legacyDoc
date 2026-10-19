"""Public metadata: languages, plans and export formats."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from legacydoc_core.billing import load_pricing
from legacydoc_core.db import get_db
from legacydoc_core.plans import PLANS
from legacydoc_exporters import ExporterFactory
from legacydoc_parsing.languages import LANGUAGES, extensions_by_language
from sqlalchemy.ext.asyncio import AsyncSession

from legacydoc_api.plan_views import plan_info
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
async def list_plans(session: AsyncSession = Depends(get_db)) -> list[PlanInfo]:
    pricing = await load_pricing(session)

    return [plan_info(plan, pricing) for plan in PLANS.values()]


@router.get("/export-formats", response_model=list[str])
async def list_export_formats() -> list[str]:
    return ExporterFactory.available_formats()
