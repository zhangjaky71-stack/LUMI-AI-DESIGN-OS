from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from lumi_api.brand_rules.service import BrandRuleService

from .errors import ApiProblem


def get_brand_rule_service() -> BrandRuleService:
    raise ApiProblem(
        status=503,
        code="brand_rule_service_not_configured",
        title="Brand Rules service unavailable",
        detail="NODE-43 Brand Rules Engine is installed but no runtime adapter is configured.",
    )


BrandRuleServiceDependency = Annotated[BrandRuleService, Depends(get_brand_rule_service)]
