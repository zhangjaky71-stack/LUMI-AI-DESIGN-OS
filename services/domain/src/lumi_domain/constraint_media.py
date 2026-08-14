# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProtectedRegionSignals:
    ssim: float
    edge_difference: float
    color_delta_e: float
    embedding_similarity: float | None = None
    evidence_ref: str | None = None


class OpenCvProtectedRegionComparator:
    """Deterministic protected-region image comparator using multiple non-LLM signals."""

    def __init__(self, image_loader: Callable[[str], bytes]) -> None:
        self._image_loader = image_loader

    def compare(
        self,
        context: Mapping[str, Any],
        constraint: Mapping[str, Any],
    ) -> ProtectedRegionSignals:
        try:
            import cv2  # type: ignore[import-not-found]
            import numpy as np  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised by fail-closed runtime
            raise RuntimeError("OpenCV protected-region comparator is unavailable") from exc

        before_ref = context.get("before_ref", {})
        after_ref = context.get("after_ref", {})
        if not isinstance(before_ref, Mapping) or not isinstance(after_ref, Mapping):
            raise RuntimeError("before_ref and after_ref are required")
        before_bytes_ref = before_ref.get("bytes_ref")
        after_bytes_ref = after_ref.get("bytes_ref")
        if not isinstance(before_bytes_ref, str) or not isinstance(after_bytes_ref, str):
            raise RuntimeError("bytes_ref is required for protected-region validation")

        before = self._decode(cv2, np, self._image_loader(before_bytes_ref))
        after = self._decode(cv2, np, self._image_loader(after_bytes_ref))
        before_crop = self._crop(before, constraint)
        after_crop = self._crop(after, constraint)
        if before_crop.shape[:2] != after_crop.shape[:2]:
            after_crop = cv2.resize(
                after_crop,
                (before_crop.shape[1], before_crop.shape[0]),
                interpolation=cv2.INTER_AREA,
            )

        before_gray = cv2.cvtColor(before_crop, cv2.COLOR_BGR2GRAY).astype("float64")
        after_gray = cv2.cvtColor(after_crop, cv2.COLOR_BGR2GRAY).astype("float64")
        ssim = self._global_ssim(np, before_gray, after_gray)

        before_edges = cv2.Canny(before_crop, 80, 160)
        after_edges = cv2.Canny(after_crop, 80, 160)
        edge_difference = float(np.mean(np.abs(before_edges.astype("float64") - after_edges.astype("float64"))) / 255.0)

        before_lab = cv2.cvtColor(before_crop, cv2.COLOR_BGR2LAB).astype("float64")
        after_lab = cv2.cvtColor(after_crop, cv2.COLOR_BGR2LAB).astype("float64")
        before_mean = np.mean(before_lab.reshape(-1, 3), axis=0)
        after_mean = np.mean(after_lab.reshape(-1, 3), axis=0)
        color_delta_e = float(np.linalg.norm(before_mean - after_mean))

        return ProtectedRegionSignals(
            ssim=ssim,
            edge_difference=edge_difference,
            color_delta_e=color_delta_e,
            evidence_ref=f"protected-region:{before_bytes_ref}:{after_bytes_ref}",
        )

    @staticmethod
    def _decode(cv2: Any, np: Any, payload: bytes) -> Any:
        encoded = np.frombuffer(payload, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("image decode failed")
        return image

    @staticmethod
    def _crop(image: Any, constraint: Mapping[str, Any]) -> Any:
        scope = constraint.get("scope", {})
        scope = scope if isinstance(scope, Mapping) else {}
        region = scope.get("region")
        if not isinstance(region, Mapping):
            return image
        height, width = image.shape[:2]
        x = max(0, min(width - 1, round(float(region.get("x", 0.0)) * width)))
        y = max(0, min(height - 1, round(float(region.get("y", 0.0)) * height)))
        region_width = max(1, round(float(region.get("width", 1.0)) * width))
        region_height = max(1, round(float(region.get("height", 1.0)) * height))
        right = max(x + 1, min(width, x + region_width))
        bottom = max(y + 1, min(height, y + region_height))
        return image[y:bottom, x:right]

    @staticmethod
    def _global_ssim(np: Any, before: Any, after: Any) -> float:
        mean_before = float(np.mean(before))
        mean_after = float(np.mean(after))
        variance_before = float(np.var(before))
        variance_after = float(np.var(after))
        covariance = float(np.mean((before - mean_before) * (after - mean_after)))
        c1 = (0.01 * 255.0) ** 2
        c2 = (0.03 * 255.0) ** 2
        numerator = (2 * mean_before * mean_after + c1) * (2 * covariance + c2)
        denominator = (
            (mean_before**2 + mean_after**2 + c1)
            * (variance_before + variance_after + c2)
        )
        if denominator <= 0:
            return 1.0 if numerator <= 0 else 0.0
        return max(-1.0, min(1.0, numerator / denominator))


class ProtectedRegionEvaluator:
    name = "protected-region"
    supported_types = frozenset({"PROTECT_REGION"})

    def __init__(self, comparator: OpenCvProtectedRegionComparator) -> None:
        self._comparator = comparator

    def evaluate(
        self,
        context: Mapping[str, Any],
        constraint: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        signals = self._comparator.compare(context, constraint)
        parameters = constraint.get("parameters", {})
        parameters = parameters if isinstance(parameters, Mapping) else {}
        min_ssim = float(parameters.get("min_ssim", 0.985))
        max_edge = float(parameters.get("max_edge_difference", 0.04))
        max_delta_e = float(parameters.get("max_color_delta_e", 3.0))
        min_embedding = parameters.get("min_embedding_similarity")
        failed = (
            signals.ssim < min_ssim
            or signals.edge_difference > max_edge
            or signals.color_delta_e > max_delta_e
            or (
                isinstance(min_embedding, (int, float))
                and signals.embedding_similarity is not None
                and signals.embedding_similarity < float(min_embedding)
            )
        )
        if not failed:
            return []
        return [
            {
                "constraint_id": str(constraint.get("id", "unknown")),
                "type": str(constraint.get("type", "PROTECT_REGION")),
                "severity": str(constraint.get("severity", "HARD")),
                "validator": self.name,
                "reason_code": "PROTECTED_REGION_CHANGED",
                "score": signals.ssim,
                "threshold": min_ssim,
                "actual": {
                    "ssim": signals.ssim,
                    "edge_difference": signals.edge_difference,
                    "color_delta_e": signals.color_delta_e,
                    "embedding_similarity": signals.embedding_similarity,
                },
                "raw_evidence_ref": signals.evidence_ref,
                "repair_hint": {"action": "restore_protected_region"},
            }
        ]
