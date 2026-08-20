from __future__ import annotations

import asyncio
import json
import socket
import tempfile
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from .errors import (
    DeliveryState,
    ErrorCategory,
    ProviderInvocationError,
    ProviderValidationError,
)
from .media_output import ProviderBinaryOutputStore
from .models import (
    Capability,
    CostConfidence,
    CostEstimate,
    ModelOutput,
    ModelRequest,
    ModelResult,
    ProviderLatencyClass,
    ProviderModel,
    ResultStatus,
    StreamChunk,
    Timing,
    Usage,
)
from .openai_adapter import HttpResponse, HttpTransport, UrllibHttpTransport

_OPENAI_VIDEOS_URL = "https://api.openai.com/v1/videos"
_SUPPORTED_MODELS = frozenset({"sora-2", "sora-2-pro"})
_SUPPORTED_SECONDS = frozenset({4, 8, 12})
_MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024
_MAX_ERROR_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class OpenAIVideoPriceCard:
    snapshot_id: str
    usd_per_second_by_size: dict[str, Decimal]

    def __post_init__(self) -> None:
        if not self.snapshot_id or len(self.snapshot_id) > 128:
            raise ValueError("OPENAI_VIDEO_PRICE_SNAPSHOT_INVALID")
        if not self.usd_per_second_by_size:
            raise ValueError("OPENAI_VIDEO_PRICE_MAP_REQUIRED")
        for size, amount in self.usd_per_second_by_size.items():
            if not isinstance(size, str) or "x" not in size or len(size) > 32:
                raise ValueError("OPENAI_VIDEO_PRICE_SIZE_INVALID")
            if not isinstance(amount, Decimal) or not amount.is_finite() or amount <= 0:
                raise ValueError("OPENAI_VIDEO_PRICE_INVALID")

    def estimate(self, *, size: str, seconds: int) -> CostEstimate:
        try:
            rate = self.usd_per_second_by_size[size]
        except KeyError as exc:
            raise ValueError("OPENAI_VIDEO_PRICE_SIZE_MISSING") from exc
        return CostEstimate(
            amount_usd=rate * Decimal(seconds),
            confidence=CostConfidence.ESTIMATED,
            price_snapshot_id=self.snapshot_id,
            detail={
                "basis": "configured_video_seconds",
                "size": size,
                "seconds": seconds,
                "usd_per_second": format(rate, "f"),
            },
        )


@dataclass(frozen=True, slots=True)
class VideoDownloadResponse:
    status: int
    headers: dict[str, str]
    error_body: bytes = b""


class VideoContentTransport(Protocol):
    def download_to_path(
        self,
        *,
        url: str,
        headers: dict[str, str],
        path: Path,
        timeout_seconds: float,
        max_bytes: int,
    ) -> VideoDownloadResponse: ...


class UrllibVideoContentTransport:
    def download_to_path(
        self,
        *,
        url: str,
        headers: dict[str, str],
        path: Path,
        timeout_seconds: float,
        max_bytes: int,
    ) -> VideoDownloadResponse:
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                response_headers = {
                    key.lower(): value for key, value in response.headers.items()
                }
                content_length = response_headers.get("content-length")
                if content_length is not None:
                    try:
                        parsed = int(content_length)
                    except ValueError as exc:
                        raise ValueError("OPENAI_VIDEO_CONTENT_LENGTH_INVALID") from exc
                    if parsed <= 0 or parsed > max_bytes:
                        raise ValueError("OPENAI_VIDEO_CONTENT_SIZE_INVALID")
                seen = 0
                with path.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        seen += len(chunk)
                        if seen > max_bytes:
                            raise ValueError("OPENAI_VIDEO_CONTENT_TOO_LARGE")
                        output.write(chunk)
                if seen <= 0:
                    raise ValueError("OPENAI_VIDEO_CONTENT_EMPTY")
                return VideoDownloadResponse(
                    status=int(response.status),
                    headers=response_headers,
                )
        except urllib.error.HTTPError as exc:
            return VideoDownloadResponse(
                status=exc.code,
                headers={key.lower(): value for key, value in exc.headers.items()},
                error_body=exc.read(_MAX_ERROR_BYTES),
            )


class OpenAIVideoGenerationAdapter:
    """Hosted async OpenAI Videos adapter.

    V1 production capability is text-to-video only. Internal Asset references are
    deliberately not converted to public/signed provider inputs here; image-to-video
    remains fail-closed until that authorization/upload boundary is implemented.
    Completed MP4 content is streamed to a temp file, then staged to the private
    provider-output bucket through ProviderBinaryOutputStore.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        price_card: OpenAIVideoPriceCard,
        output_store: ProviderBinaryOutputStore,
        transport: HttpTransport | None = None,
        content_transport: VideoContentTransport | None = None,
        organization: str | None = None,
        project: str | None = None,
        timeout_seconds: float = 180.0,
        download_timeout_seconds: float = 600.0,
        quality_score: int = 94,
        max_video_bytes: int = _MAX_VIDEO_BYTES,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_VIDEO_API_KEY_REQUIRED")
        if model not in _SUPPORTED_MODELS:
            raise ValueError("OPENAI_VIDEO_MODEL_UNSUPPORTED")
        if not 1 <= timeout_seconds <= 600:
            raise ValueError("OPENAI_VIDEO_TIMEOUT_INVALID")
        if not 1 <= download_timeout_seconds <= 3600:
            raise ValueError("OPENAI_VIDEO_DOWNLOAD_TIMEOUT_INVALID")
        if not 0 <= quality_score <= 100:
            raise ValueError("OPENAI_VIDEO_QUALITY_SCORE_INVALID")
        if not 1 <= max_video_bytes <= _MAX_VIDEO_BYTES:
            raise ValueError("OPENAI_VIDEO_MAX_BYTES_INVALID")
        self._api_key = api_key
        self._organization = organization
        self._project = project
        self._price_card = price_card
        self._output_store = output_store
        self._transport = transport or UrllibHttpTransport()
        self._content_transport = content_transport or UrllibVideoContentTransport()
        self._timeout_seconds = timeout_seconds
        self._download_timeout_seconds = download_timeout_seconds
        self._max_video_bytes = max_video_bytes
        self._descriptor = ProviderModel(
            provider="openai",
            model=model,
            capabilities=frozenset({Capability.VIDEO_TEXT_TO_VIDEO}),
            quality_score=quality_score,
            latency_class=ProviderLatencyClass.SLOW,
            supports_streaming=False,
            supports_async=True,
        )

    @property
    def descriptor(self) -> ProviderModel:
        return self._descriptor

    def validate(self, request: ModelRequest) -> None:
        if request.capability != Capability.VIDEO_TEXT_TO_VIDEO:
            raise self._validation(
                "hosted OpenAI video adapter currently exposes text-to-video only"
            )
        if request.reference_assets:
            raise self._validation(
                "image references require a controlled asset-to-provider input boundary"
            )
        self._prompt(request)
        self._seconds(request)
        size = self._size(request)
        if size not in self._price_card.usd_per_second_by_size:
            raise self._validation(
                "requested video size is not enabled by the pinned price card",
                category=ErrorCategory.HARD_CONSTRAINT_INVALID,
            )
        seed = request.inputs.get("seed")
        if seed is not None:
            raise self._validation(
                "deterministic seed is not supported by the hosted OpenAI video adapter",
                category=ErrorCategory.HARD_CONSTRAINT_INVALID,
            )

    async def estimate_cost(self, request: ModelRequest) -> CostEstimate:
        self.validate(request)
        return self._price_card.estimate(
            size=self._size(request),
            seconds=self._seconds(request),
        )

    async def invoke(self, request: ModelRequest) -> ModelResult:
        self.validate(request)
        seconds = self._seconds(request)
        size = self._size(request)
        body = json.dumps(
            {
                "model": self._descriptor.model,
                "prompt": self._prompt(request),
                "seconds": str(seconds),
                "size": size,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            response = await asyncio.to_thread(
                self._transport.request,
                method="POST",
                url=_OPENAI_VIDEOS_URL,
                headers=self._headers(content_type="application/json"),
                body=body,
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            raise self.normalize_error(exc) from exc
        elapsed_ms = int((loop.time() - started) * 1000)
        if not 200 <= response.status < 300:
            raise self._http_error(response, paid_request=True)
        job = self._parse_job(response.body)
        if job["status"] == "failed":
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                self._job_error_message(job),
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.ACCEPTED,
            )
        return ModelResult(
            status=ResultStatus.PENDING,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            provider_request_id=job["id"],
            outputs=(),
            usage=Usage(seconds=Decimal(seconds)),
            timing=Timing(total_ms=elapsed_ms),
            cost=self._price_card.estimate(size=size, seconds=seconds),
            safety_metadata={"provider_status": job["status"]},
            finish_reason="queued" if job["status"] == "queued" else "in_progress",
        )

    async def get_async_status(self, provider_request_id: str) -> ModelResult:
        self._provider_request_id(provider_request_id)
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            response = await asyncio.to_thread(
                self._transport.request,
                method="GET",
                url=f"{_OPENAI_VIDEOS_URL}/{provider_request_id}",
                headers=self._headers(),
                body=None,
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            raise self.normalize_error(exc) from exc
        elapsed_ms = int((loop.time() - started) * 1000)
        if not 200 <= response.status < 300:
            raise self._http_error(response, paid_request=False)
        job = self._parse_job(response.body)
        if job["id"] != provider_request_id:
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI video job identity changed",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        seconds = self._job_seconds(job)
        size = self._job_size(job)
        cost = self._price_card.estimate(size=size, seconds=seconds)
        status = job["status"]
        if status in {"queued", "in_progress"}:
            return ModelResult(
                status=ResultStatus.PENDING,
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                provider_request_id=provider_request_id,
                outputs=(),
                usage=Usage(seconds=Decimal(seconds)),
                timing=Timing(total_ms=elapsed_ms),
                cost=cost,
                safety_metadata={"provider_status": status},
                finish_reason=status,
            )
        if status == "failed":
            return ModelResult(
                status=ResultStatus.FAILED,
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                provider_request_id=provider_request_id,
                outputs=(),
                usage=Usage(seconds=Decimal(seconds)),
                timing=Timing(total_ms=elapsed_ms),
                cost=cost,
                safety_metadata={
                    "provider_status": status,
                    "provider_error": self._job_error_code(job),
                },
                finish_reason="failed",
            )
        if status != "completed":
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI video returned an unknown job status",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        asset_ref = await self._download_completed(provider_request_id)
        return ModelResult(
            status=ResultStatus.SUCCEEDED,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            provider_request_id=provider_request_id,
            outputs=(
                ModelOutput(
                    kind="asset_ref",
                    value=asset_ref,
                    mime_type="video/mp4",
                ),
            ),
            usage=Usage(seconds=Decimal(seconds)),
            timing=Timing(total_ms=elapsed_ms),
            cost=cost,
            safety_metadata={"provider_status": status},
            finish_reason="completed",
        )

    async def cancel(self, provider_request_id: str) -> ModelResult:
        self._provider_request_id(provider_request_id)
        raise ProviderInvocationError(
            ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE,
            "OpenAI Videos exposes delete but this adapter does not equate deletion with proven cancellation",
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.NOT_ACCEPTED,
        )

    def stream(self, request: ModelRequest) -> AsyncIterator[StreamChunk]:
        async def unsupported() -> AsyncIterator[StreamChunk]:
            del request
            raise ProviderInvocationError(
                ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE,
                "video generation does not expose token streaming",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
            yield  # pragma: no cover

        return unsupported()

    def normalize_error(self, error: Exception) -> ProviderInvocationError:
        if isinstance(error, ProviderInvocationError):
            return error
        if isinstance(error, (TimeoutError, socket.timeout)):
            category = ErrorCategory.TIMEOUT
        elif isinstance(error, urllib.error.URLError):
            category = ErrorCategory.PROVIDER_UNAVAILABLE
        else:
            category = ErrorCategory.UNKNOWN
        return ProviderInvocationError(
            category,
            "OpenAI video network/output outcome is unknown",
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.UNKNOWN,
        )

    async def _download_completed(self, provider_request_id: str) -> str:
        with tempfile.TemporaryDirectory(prefix="lumi-openai-video-") as directory:
            path = Path(directory) / "provider.mp4"
            try:
                response = await asyncio.to_thread(
                    self._content_transport.download_to_path,
                    url=f"{_OPENAI_VIDEOS_URL}/{provider_request_id}/content",
                    headers=self._headers(),
                    path=path,
                    timeout_seconds=self._download_timeout_seconds,
                    max_bytes=self._max_video_bytes,
                )
            except Exception as exc:
                raise self.normalize_error(exc) from exc
            if not 200 <= response.status < 300:
                raise self._http_error(
                    HttpResponse(
                        status=response.status,
                        headers=response.headers,
                        body=response.error_body,
                    ),
                    paid_request=False,
                )
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type and content_type != "video/mp4":
                raise ProviderInvocationError(
                    ErrorCategory.UNKNOWN,
                    "OpenAI completed video content type is not video/mp4",
                    provider=self._descriptor.provider,
                    model=self._descriptor.model,
                    delivery_state=DeliveryState.NOT_ACCEPTED,
                )
            return await self._output_store.store_async_path(
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                provider_request_id=provider_request_id,
                path=path,
                content_type="video/mp4",
                extension="mp4",
                max_bytes=self._max_video_bytes,
            )

    def _headers(self, *, content_type: str | None = None) -> dict[str, str]:
        headers = {"authorization": f"Bearer {self._api_key}"}
        if content_type:
            headers["content-type"] = content_type
        if self._organization:
            headers["openai-organization"] = self._organization
        if self._project:
            headers["openai-project"] = self._project
        return headers

    def _prompt(self, request: ModelRequest) -> str:
        prompt = request.inputs.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise self._validation("video prompt is required")
        value = prompt.strip()
        if len(value) > 32_000:
            raise self._validation("video prompt exceeds provider limit")
        return value

    def _seconds(self, request: ModelRequest) -> int:
        raw = request.constraints.get("duration_seconds", request.inputs.get("duration_seconds"))
        try:
            value = int(str(raw))
        except (TypeError, ValueError) as exc:
            raise self._validation("video duration is invalid") from exc
        if str(value) != str(raw).strip() or value not in _SUPPORTED_SECONDS:
            raise self._validation(
                "hosted OpenAI video duration must be exactly 4, 8, or 12 seconds",
                category=ErrorCategory.HARD_CONSTRAINT_INVALID,
            )
        return value

    def _size(self, request: ModelRequest) -> str:
        width = request.constraints.get("width", request.inputs.get("width"))
        height = request.constraints.get("height", request.inputs.get("height"))
        if (
            isinstance(width, bool)
            or isinstance(height, bool)
            or not isinstance(width, int)
            or not isinstance(height, int)
            or width <= 0
            or height <= 0
        ):
            raise self._validation("video width/height are required")
        return f"{width}x{height}"

    def _parse_job(self, body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI video returned invalid JSON",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI video returned a non-object response",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        job_id = payload.get("id")
        status = payload.get("status")
        if not isinstance(job_id, str) or not job_id or len(job_id) > 512:
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI video response is missing job id",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        if status not in {"queued", "in_progress", "completed", "failed"}:
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI video response has invalid status",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        return payload

    def _job_seconds(self, job: dict[str, Any]) -> int:
        raw = job.get("seconds")
        try:
            value = int(str(raw))
        except (TypeError, ValueError) as exc:
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI video job is missing duration",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            ) from exc
        if value not in _SUPPORTED_SECONDS:
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI video job returned unsupported duration",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        return value

    def _job_size(self, job: dict[str, Any]) -> str:
        size = job.get("size")
        if not isinstance(size, str) or size not in self._price_card.usd_per_second_by_size:
            raise ProviderInvocationError(
                ErrorCategory.UNKNOWN,
                "OpenAI video job returned an unpriced size",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        return size

    def _provider_request_id(self, value: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 512
            or value != value.strip()
            or any(char in value for char in ("\x00", "\n", "\r", "/", "?", "#"))
        ):
            raise ProviderInvocationError(
                ErrorCategory.INVALID_REQUEST,
                "invalid OpenAI video job id",
                provider=self._descriptor.provider,
                model=self._descriptor.model,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        return value

    def _job_error_code(self, job: dict[str, Any]) -> str | None:
        error = job.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return error["code"][:200]
        return None

    def _job_error_message(self, job: dict[str, Any]) -> str:
        error = job.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:1000]
        return "OpenAI video generation failed"

    def _http_error(self, response: HttpResponse, *, paid_request: bool) -> ProviderInvocationError:
        category = ErrorCategory.UNKNOWN
        if response.status == 429:
            category = ErrorCategory.RATE_LIMIT
        elif response.status in {408, 409, 425} or response.status >= 500:
            category = ErrorCategory.PROVIDER_UNAVAILABLE
        elif 400 <= response.status < 500:
            category = ErrorCategory.INVALID_REQUEST
        message = f"OpenAI video HTTP {response.status}"
        try:
            payload = json.loads(response.body)
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict) and isinstance(error.get("message"), str):
                    message = error["message"][:1000]
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        delivery = (
            DeliveryState.UNKNOWN
            if paid_request and response.status >= 500
            else DeliveryState.NOT_ACCEPTED
        )
        return ProviderInvocationError(
            category,
            message,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=delivery,
        )

    def _validation(
        self,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.INVALID_REQUEST,
    ) -> ProviderValidationError:
        return ProviderValidationError(
            category,
            message,
            provider=self._descriptor.provider,
            model=self._descriptor.model,
            delivery_state=DeliveryState.NOT_ACCEPTED,
        )
