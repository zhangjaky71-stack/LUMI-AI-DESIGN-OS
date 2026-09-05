from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .contracts import ProblemDetails, ProblemField


class ApiProblem(Exception):
    def __init__(
        self,
        *,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        problem_type: str = "about:blank",
        errors: list[ProblemField] | None = None,
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.problem_type = problem_type
        self.errors = errors or []


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "missing-request-id"))


def _problem_response(problem: ProblemDetails) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        media_type="application/problem+json",
        content=problem.model_dump(mode="json", exclude_none=True),
    )


async def api_problem_handler(request: Request, exc: ApiProblem) -> JSONResponse:
    problem = ProblemDetails(
        type=exc.problem_type,
        title=exc.title,
        status=exc.status,
        detail=exc.detail,
        instance=str(request.url.path),
        code=exc.code,
        request_id=_request_id(request),
        errors=exc.errors,
    )
    return _problem_response(problem)


async def validation_problem_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    fields: list[ProblemField] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", ()))
        fields.append(
            ProblemField(
                field=location,
                code=str(error.get("type", "validation_error")),
                message=str(error.get("msg", "Invalid request")),
            )
        )
    return _problem_response(
        ProblemDetails(
            title="Request validation failed",
            status=422,
            detail="One or more request fields are invalid.",
            instance=str(request.url.path),
            code="REQUEST_VALIDATION_FAILED",
            request_id=_request_id(request),
            errors=fields,
        )
    )


def problem_responses() -> dict[int | str, dict[str, Any]]:
    schema = {"model": ProblemDetails, "content": {"application/problem+json": {}}}
    return {
        400: schema,
        404: schema,
        409: schema,
        422: schema,
        428: schema,
        429: schema,
        500: schema,
        503: schema,
    }
